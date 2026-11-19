"""Compare committed rule records without choosing or applying a merge."""

import re
from pathlib import Path

from paperrule.domain.models import RuleRecord, digest
from paperrule.sync.git import GitSync, SyncError

RULE_PATH = re.compile(
    r"rules/(global|research-type|publication|paper|section-task)/"
    r"([A-Za-z0-9][A-Za-z0-9_-]{0,100})[.]json"
)
FOLDERS = {
    "global": "global", "research_type": "research-type",
    "publication": "publication", "paper": "paper", "section_task": "section-task",
}


def _rules_at(git: GitSync, commit: str) -> dict[str, dict]:
    records = {}
    tree = git.run("ls-tree", "-r", "-z", "--full-tree", commit, "--", "rules")
    for entry in tree.split(chr(0)):
        if not entry:
            continue
        metadata, path = entry.split(chr(9), 1)
        if not path.endswith(".json"):
            continue
        mode, kind, object_id = metadata.split()
        match = RULE_PATH.fullmatch(path)
        if match is None or kind != "blob" or mode not in {"100644", "100755"}:
            raise SyncError("Unsupported rule tree entry; no rules were applied")
        try:
            text = git.read_blob(object_id).decode("utf-8", errors="strict")
            rule = RuleRecord.model_validate_json(text)
        except (UnicodeDecodeError, ValueError) as exc:
            raise SyncError("Committed rule record is invalid; no rules were applied") from exc
        folder, file_id = match.groups()
        level = rule.scope.levels[-1] if rule.scope.levels else "global"
        if rule.id != file_id or folder != FOLDERS.get(level, "global"):
            raise SyncError("Rule path and record identity disagree")
        if rule.id in records:
            raise SyncError("Committed tree contains duplicate rule identifiers")
        records[rule.id] = {
            "path": path, "blob_sha": object_id, "rule_sha256": digest(rule),
            "rule": rule.model_dump(mode="json"),
        }
    return records


def _identity(record: dict | None) -> tuple[str, str] | None:
    return (record["path"], record["blob_sha"]) if record is not None else None


def preview_rule_divergence(git: GitSync, *, fetch: bool = True) -> dict:
    """Fetch origin refs, then describe base/local/remote committed rule records.

    Fetching can update Git objects and remote-tracking refs. This function does
    not check out files, stage changes, commit, push, approve, or resolve a rule.
    Attachments, non-rule records and merge application are outside this preview.
    """
    actual = Path(git.run("rev-parse", "--show-toplevel")).resolve()
    if actual != git.root:
        raise SyncError("Memory must be a dedicated Git repository")
    if "origin" not in git.run("remote").splitlines():
        raise SyncError("No origin remote configured")
    upstream = git.run("rev-parse", "--symbolic-full-name", "@{upstream}")
    if not upstream.startswith("refs/remotes/origin/"):
        raise SyncError("Memory upstream must belong to origin")
    if fetch:
        git.run("fetch", "--no-tags", "origin")
    local = git.validate_sha(git.head())
    remote = git.validate_sha(git.run("rev-parse", "--verify", upstream + "^{commit}"))
    base = git.run("merge-base", local, remote, check=False)
    if not base:
        raise SyncError("Memory histories have no common ancestor; explicit review is required")
    base = git.validate_sha(base)
    snapshots = {
        "base": _rules_at(git, base),
        "local": _rules_at(git, local),
        "remote": _rules_at(git, remote),
    }
    identifiers = set().union(*(records.keys() for records in snapshots.values()))
    changes = []
    for rule_id in sorted(identifiers):
        versions = {side: records.get(rule_id) for side, records in snapshots.items()}
        original, here, there = (_identity(versions[side]) for side in ("base", "local", "remote"))
        if here == there:
            continue
        kind = (
            "remote_change" if here == original
            else "local_change" if there == original else "both_changed"
        )
        changes.append({"rule_id": rule_id, "kind": kind, **versions})
    status = (
        "same" if local == remote else "ahead" if base == remote
        else "behind" if base == local else "diverged"
    )
    payload = {
        "status": status, "local_commit": local, "remote_commit": remote,
        "base_commit": base, "upstream_ref": upstream,
        "working_tree_dirty": bool(git.run("status", "--porcelain")),
        "staged_changes": bool(git.run("diff", "--cached", "--name-only")),
        "scope": "committed_rule_records_only",
        "applies_changes": False, "requires_approval": True,
        "changes": changes,
    }
    return {**payload, "preview_sha256": digest(payload)}
