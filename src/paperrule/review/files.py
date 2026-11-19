"""Read manuscript changes without running paper-provided commands or Git hooks."""

import difflib
import hashlib
import json
import os
import subprocess
from pathlib import Path
from uuid import uuid4

from paperrule.domain.models import PaperProfile, ReviewReport
from paperrule.persistence.store import MemoryStore
from paperrule.providers import CodexCLIProvider, OpenAIAPIProvider
from paperrule.providers.base import AIProvider
from paperrule.review.check import check_text
from paperrule.review.selection import select_review_rules
from paperrule.sync.git import GitSync

TEXT_SUFFIXES = {".tex", ".bib", ".md", ".txt"}
MAX_FILE_BYTES = 5 * 1024 * 1024


def _git(root: Path, *args: str, required: bool = True) -> bytes:
    result = subprocess.run(
        ["git", "-c", "core.hooksPath=", "-c", "core.fsmonitor=false", *args],
        cwd=root, capture_output=True, timeout=30, check=False,
    )
    if required and result.returncode:
        raise ValueError("Cannot read manuscript Git state; select an initialized paper repository")
    return result.stdout if result.returncode == 0 else b""


def changed_documents(root: Path) -> tuple[list[dict], str]:
    root = root.resolve(strict=True)
    actual = Path(_git(root, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    if actual != root:
        raise ValueError("Paper project must be the root of its own Git repository")
    commit = _git(root, "rev-parse", "--verify", "HEAD").decode("ascii").strip()
    names = _git(root, "diff", "--name-only", "-z", "--no-ext-diff", "HEAD", "--")
    names += _git(root, "ls-files", "--others", "--exclude-standard", "-z")
    documents = []
    for raw in sorted(set(names.split(bytes([0]))) - {b""}):
        relative = raw.decode("utf-8")
        path = root / relative
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise ValueError("A changed manuscript file escapes its paper project")
        previous = _git(root, "show", commit + ":" + relative, required=False)
        current = path.read_bytes() if path.is_file() else b""
        if max(len(previous), len(current)) > MAX_FILE_BYTES:
            raise ValueError("Manuscript text exceeds the 5 MiB review limit")
        before = previous.decode("utf-8-sig")
        after = current.decode("utf-8-sig")
        old_lines, new_lines = before.splitlines(), after.splitlines()
        changed_lines = set()
        matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
        for operation, _, _, start, end in matcher.get_opcodes():
            if operation in {"replace", "insert"}:
                changed_lines.update(range(start + 1, end + 1))
        documents.append({
            "path": relative, "text": after, "changed_lines": changed_lines,
            "sha256": hashlib.sha256(current).hexdigest(),
            "diff": chr(10).join(difflib.unified_diff(
                old_lines, new_lines, fromfile="a/" + relative,
                tofile="b/" + relative, lineterm="",
            )),
        })
    return documents, commit


def check_documents(
    store: MemoryStore, documents: list[dict], profile: PaperProfile | None = None,
    *, section: str = "", task: str = "", paper_commit: str | None = None,
    diff_mode: bool = False,
    semantic: bool = False, semantic_provider: AIProvider | None = None,
    max_semantic_calls: int = 8,
) -> dict:
    with store.locked(wait=5):
        all_rules = store.rules()
        selection = select_review_rules(all_rules, profile, section, task)
        rules = selection.rules
        memory_git = GitSync(store.root)
        memory_commit = memory_git.head() if (store.root / ".git").exists() else None
        memory_commit = memory_commit or None
        memory_rules_dirty = (
            bool(memory_git.run("status", "--porcelain", "--", "rules"))
            if memory_commit else True
        )
    snapshot = [rule.model_dump(mode="json") for rule in rules]
    snapshot_hash = hashlib.sha256(json.dumps(
        snapshot, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    unavailable = selection.unavailable + [
        {"rule_id": rule.id, "rule_version": rule.version,
         "reason": selection.blocked.get(rule.id) or (
         "semantic_not_reviewed" if rule.check_method == "semantic"
         else "semantic_exception_not_reviewed" if rule.scope.exceptions
         else "deterministic_check_not_supported")}
        for rule in rules if rule.id in selection.blocked or rule.check_method != "deterministic"
        or rule.scope.exceptions
        or not rule.statement.casefold().startswith("avoid: ")
        or not rule.statement[7:].strip()
    ]
    findings = []
    phrase_rules = [
        rule for rule in rules if not rule.scope.exceptions and rule.id not in selection.blocked
    ]
    checked_line_count = 0
    for document in documents:
        for number, line in enumerate(document["text"].splitlines(), 1):
            if diff_mode and number not in document["changed_lines"]:
                continue
            checked_line_count += 1
            for finding in check_text(line, phrase_rules):
                finding.location = document["path"] + ":" + str(number)
                finding.quote = line
                findings.append(finding.model_dump(mode="json"))
    unsupported = {item["rule_id"]: item["reason"] for item in unavailable}
    coverage = [{
        "rule_id": rule.id, "rule_version": rule.version,
        "status": "not_reviewed" if not checked_line_count
        else "unavailable" if rule.id in unsupported else "checked",
        "reason": "no_lines_in_selected_input" if not checked_line_count
        else unsupported.get(rule.id, "deterministic_phrase_check"),
        "checked_line_count": (
            checked_line_count if rule.id not in unsupported else 0
        ),
    } for rule in rules]
    payload = {
        "review_id": "REV-" + uuid4().hex[:16],
        "paper_id": profile.paper_id if profile else None,
        "task_summary": task or ("Review changed manuscript lines" if diff_mode
                                 else "Review manuscript text"),
        "source": "paperrule_check", "provider": "deterministic",
        "section": section, "task": task, "diff_mode": diff_mode,
        "paper_commit": paper_commit, "memory_commit": memory_commit,
        "memory_rules_dirty": memory_rules_dirty,
        "rule_snapshot": snapshot, "rule_snapshot_sha256": snapshot_hash,
        "selection_notes": selection.notes, "unresolved": selection.unresolved,
        "coverage": coverage,
        "status": "not_reviewed" if not checked_line_count or not rules
        else "incomplete" if unavailable else "findings" if findings else "checked",
        "findings": findings, "unavailable": unavailable,
        "rules": [{"rule_id": rule.id, "version": rule.version} for rule in rules],
        "files": [{key: value for key, value in document.items()
                   if key not in {"text", "changed_lines"}} for document in documents],
        "semantic_status": "not_reviewed",
        "latex_build_status": "not_run",
    }
    if semantic:
        from paperrule.review.semantic_checks import augment_semantic_review

        factories = {
            "openai": OpenAIAPIProvider, "openai_api": OpenAIAPIProvider,
            "codex": CodexCLIProvider, "codex_cli": CodexCLIProvider,
        }
        factory = factories.get(os.environ.get("PAPERRULE_PROVIDER", "manual").casefold())
        provider = semantic_provider if semantic_provider is not None else (
            factory() if factory else None
        )
        augment_semantic_review(
            payload, documents, rules, provider, max_calls=max_semantic_calls,
            blocked=selection.blocked,
        )
    report = ReviewReport.model_validate(payload)
    with store.locked(wait=5):
        store.save_review(report)
    return report.model_dump(mode="json")
