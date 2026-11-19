"""Read committed private-memory evidence without checking out any files."""

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from math import isfinite
from pathlib import Path

from paperrule.domain.models import (
    ApprovalEvent,
    ChangeProposal,
    FeedbackItem,
    PaperProfile,
    RegressionCase,
    ReviewerProfile,
    ReviewReport,
    RuleRecord,
    SourceRecord,
    digest,
)
from paperrule.sync.git import GitSync, SyncError
from paperrule.sync.paths import classify_memory_path, validate_memory_entries
from paperrule.sync.preview import FOLDERS

MODELS = {
    "sources": (SourceRecord, "id"),
    "feedback": (FeedbackItem, "id"),
    "proposals": (ChangeProposal, "proposal_id"),
    "decisions": (ApprovalEvent, "event_id"),
    "papers": (PaperProfile, "paper_id"),
    "reviewers": (ReviewerProfile, "reviewer_id"),
    "reviews": (ReviewReport, "review_id"),
    "regression": (RegressionCase, "id"),
}


@dataclass(frozen=True)
class InventoryLimits:
    files: int = 10000
    json_bytes: int = 2_000_000
    attachment_bytes: int = 25 * 1024 * 1024
    total_bytes: int = 128 * 1024 * 1024

    def __post_init__(self):
        values = (self.files, self.json_bytes, self.attachment_bytes, self.total_bytes)
        if any(type(value) is not int or not value > 0 for value in values):
            raise ValueError("Inventory limits must be positive integers")


@dataclass(frozen=True)
class MemoryBlob:
    path: str
    mode: str
    object_id: str
    category: str
    data: bytes
    sha256: str
    record: dict | None = None


@dataclass(frozen=True)
class MemoryInventory:
    commit: str
    entries: dict[str, MemoryBlob]
    total_bytes: int
    inventory_sha256: str


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON member")
        result[key] = value
    return result


def _constant(value):
    raise ValueError("Nonfinite JSON number")


def _finite_float(value):
    number = float(value)
    if not isfinite(number):
        raise ValueError("Nonfinite JSON number")
    return number


def _record(path: str, data: bytes) -> dict:
    value = json.loads(
        data.decode("utf-8", errors="strict"),
        object_pairs_hook=_object, parse_constant=_constant, parse_float=_finite_float,
    )
    if not isinstance(value, dict):
        raise TypeError("Memory records must be JSON objects")
    parts = path.split("/")
    stem = parts[-1][:-5]
    folder = parts[0]
    if path == "manifest.json":
        if (type(value.get("schema_version")) is not int
                or value["schema_version"] != 1 or value.get("product") != "PaperRule"):
            raise ValueError("Unsupported committed memory manifest")
    elif folder in MODELS:
        model, field = MODELS[folder]
        parsed = model.model_validate(value)
        if getattr(parsed, field) != stem:
            raise ValueError("Record path and identity disagree")
    elif folder in {"rules", "history", "tasks"}:
        rule = RuleRecord.model_validate(value)
        if folder == "rules":
            level = rule.scope.levels[-1] if rule.scope.levels else "global"
            if stem != rule.id or parts[1] != FOLDERS.get(level, "global"):
                raise ValueError("Rule path and identity disagree")
        elif folder == "history" and stem != f"{rule.id}-v{rule.version}":
            raise ValueError("Historical rule path and version disagree")
        # One-off tasks are keyed by proposal ID, not by the embedded rule ID.
    elif folder == "snapshots":
        if set(value) != {"approval", "rules"} or not isinstance(value["rules"], list):
            raise ValueError("Invalid approval snapshot")
        event = ApprovalEvent.model_validate(value["approval"])
        if event.event_id != stem:
            raise ValueError("Snapshot path and approval identity disagree")
        for rule in value["rules"]:
            RuleRecord.model_validate(rule)
    elif folder in {"analyses", "runs"}:
        field = "analysis_id" if folder == "analyses" else "run_id"
        if value.get(field) != stem:
            raise ValueError("Report path and identity disagree")
    return value


def _sources(entries: dict[str, MemoryBlob]) -> None:
    sources = {
        blob.record["id"]: SourceRecord.model_validate(blob.record)
        for path, blob in entries.items() if path.startswith("sources/")
    }
    for source in sources.values():
        if classify_memory_path(source.attachment) != "attachment":
            raise ValueError("Source must reference a committed attachment")
        attachment = entries.get(source.attachment)
        if attachment is None or attachment.sha256 != source.sha256:
            raise ValueError("Source attachment is absent or its original hash disagrees")
        name = source.attachment.split("/")[-1]
        if name != source.id and not name.startswith(source.id + "."):
            raise ValueError("Attachment path and source identity disagree")
        pair = source.revision_pair
        if pair is not None:
            for source_id, expected in (
                (pair.before_source_id, pair.before_sha256),
                (pair.after_source_id, pair.after_sha256),
            ):
                original = sources.get(source_id)
                if original is None or original.sha256 != expected:
                    raise ValueError("Revision pair original source binding disagrees")


def read_memory_inventory(
    git: GitSync, commit: str, *, limits: InventoryLimits | None = None,
) -> MemoryInventory:
    """Validate all supported committed files; never follow metadata paths.

    This is evidence for a future merge plan, not an approval or application.
    Arbitrary dictionaries in examples and reports receive JSON validation,
    rather than an invented schema. External attachment storage is unsupported
    here and must not be silently represented as a verified local attachment.
    """
    limits = limits or InventoryLimits()
    if not re.fullmatch("[a-f0-9]{40}", commit):
        raise SyncError("Inventory requires a full commit identity")
    if Path(git.run("rev-parse", "--show-toplevel")).resolve() != git.root:
        raise SyncError("Memory must be a dedicated Git repository")
    commit = git.validate_sha(commit)
    tree = git.run("ls-tree", "-r", "-z", "--full-tree", commit)
    rows = []
    try:
        for item in tree.split(chr(0)):
            if item:
                metadata, path = item.split(chr(9), 1)
                mode, kind, object_id = metadata.split()
                rows.append((path, mode, kind, object_id))
                if len(rows) > limits.files:
                    raise ValueError("Committed inventory file count exceeds its limit")
        categories = validate_memory_entries([
            (path, mode, kind) for path, mode, kind, _ in rows
        ])
        entries = {}
        rule_ids = set()
        total = 0
        for path, mode, _, object_id in rows:
            category = categories[path]
            per_file = limits.attachment_bytes if category == "attachment" else limits.json_bytes
            data = git.read_blob(object_id, max_bytes=min(per_file, limits.total_bytes - total))
            total += len(data)
            record = _record(path, data) if category in {"manifest", "record"} else None
            if category == "ignore":
                data.decode("utf-8", errors="strict")
            if path.startswith("rules/"):
                folded = record["id"].casefold()
                if folded in rule_ids:
                    raise ValueError("Duplicate committed rule identity")
                rule_ids.add(folded)
            entries[path] = MemoryBlob(
                path, mode, object_id, category, data, sha256(data).hexdigest(), record,
            )
        if "manifest.json" not in entries:
            raise ValueError("Committed memory manifest is missing")
        _sources(entries)
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise SyncError("Committed memory inventory is invalid; no files were applied") from exc
    binding = {
        "commit": commit,
        "files": [{
            "path": blob.path, "mode": blob.mode, "blob": blob.object_id,
            "sha256": blob.sha256, "category": blob.category,
        } for _, blob in sorted(entries.items())],
    }
    return MemoryInventory(commit, entries, total, digest(binding))
