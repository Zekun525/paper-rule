"""Read manuscript changes without running paper-provided commands or Git hooks."""

import difflib
import hashlib
import subprocess
from pathlib import Path

from paperrule.domain.models import PaperProfile
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import applies
from paperrule.review.check import check_text
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
) -> dict:
    with store.locked(wait=5):
        rules = [rule for rule in store.rules() if rule.status.value == "active"]
        memory_commit = GitSync(store.root).head() or None
        if profile:
            rules = [rule for rule in rules if applies(rule, profile, section, task)[0]]
        else:
            rules = [rule for rule in rules if not any((
                rule.scope.paper_ids, rule.scope.sections, rule.scope.task_types,
                rule.scope.research_types, rule.scope.venues, rule.scope.article_types,
                rule.scope.include, rule.scope.exclude, rule.scope.exceptions,
                rule.scope.effective_from,
            ))]
    unavailable = [
        {"rule_id": rule.id, "rule_version": rule.version,
         "reason": "semantic_not_reviewed" if rule.check_method == "semantic"
         else "deterministic_check_not_supported"}
        for rule in rules if rule.check_method != "deterministic"
        or not rule.statement.casefold().startswith("avoid: ")
        or not rule.statement[7:].strip()
    ]
    findings = []
    for document in documents:
        for number, line in enumerate(document["text"].splitlines(), 1):
            if diff_mode and number not in document["changed_lines"]:
                continue
            for finding in check_text(line, rules):
                finding.location = document["path"] + ":" + str(number)
                finding.quote = line
                findings.append(finding.model_dump(mode="json"))
    return {
        "paper_id": profile.paper_id if profile else None,
        "section": section, "task": task, "diff_mode": diff_mode,
        "paper_commit": paper_commit, "memory_commit": memory_commit,
        "status": "incomplete" if unavailable else "findings" if findings
        else "checked" if documents and rules else "not_reviewed",
        "findings": findings, "unavailable": unavailable,
        "rules": [{"rule_id": rule.id, "version": rule.version} for rule in rules],
        "files": [{key: value for key, value in document.items()
                   if key not in {"text", "changed_lines"}} for document in documents],
        "semantic_status": "not_reviewed",
        "latex_build_status": "not_run",
    }
