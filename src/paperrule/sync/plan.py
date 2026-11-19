"""Prepare a reviewable three-way file plan without resolving conflicts."""

from paperrule.domain.models import digest
from paperrule.sync.inventory import MemoryBlob, MemoryInventory


def _reference(blob: MemoryBlob | None) -> dict | None:
    if blob is None:
        return None
    return {
        "path": blob.path, "mode": blob.mode, "blob_sha": blob.object_id,
        "sha256": blob.sha256, "category": blob.category,
    }


def prepare_file_plan(
    base: MemoryInventory, local: MemoryInventory, remote: MemoryInventory,
) -> dict:
    """Bind every committed file to three inventories for subsequent review.

    One-sided choices are recommendations only. Conflicting bytes, deletions
    and modes remain unresolved, including collisions in historical records.
    This function neither persists a proposal nor grants approval or writes
    memory. A later approval service must independently validate freshness,
    resulting path collisions, references and authority before application.
    """
    files = []
    conflicts = 0
    for path in sorted(set(base.entries) | set(local.entries) | set(remote.entries)):
        versions = {
            "base": _reference(base.entries.get(path)),
            "local": _reference(local.entries.get(path)),
            "remote": _reference(remote.entries.get(path)),
        }
        original, here, there = (versions[side] for side in ("base", "local", "remote"))
        if here == there:
            state, selected = "same", "local"
        elif here == original:
            state, selected = "remote_change", "remote"
        elif there == original:
            state, selected = "local_change", "local"
        else:
            state, selected = "conflict", None
            conflicts += 1
        files.append({
            "path": path, "state": state, "recommended_side": selected,
            "requires_decision": selected is None, **versions,
        })
    payload = {
        "schema_version": 1,
        "base_commit": base.commit, "local_commit": local.commit,
        "remote_commit": remote.commit,
        "inventory_bindings": {
            "base": base.inventory_sha256, "local": local.inventory_sha256,
            "remote": remote.inventory_sha256,
        },
        "files": files, "conflict_count": conflicts,
        "requires_approval": True, "applies_changes": False,
        "status": "unresolved" if conflicts else "awaiting_review",
    }
    return {**payload, "plan_sha256": digest(payload)}
