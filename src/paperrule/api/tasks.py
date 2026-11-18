from fastapi import FastAPI, HTTPException

from paperrule.domain.models import RuleRecord, digest
from paperrule.persistence.store import MemoryStore, identifier, proposal_digest


def register_tasks(app: FastAPI, store: MemoryStore) -> None:
    @app.get("/api/tasks")
    def tasks():
        """List only task records bound to an explicitly approved proposal."""
        with store.locked(wait=5):
            records = []
            for proposal in store.proposals():
                if proposal.operation != "one_off" or not proposal.approved_hash:
                    continue
                try:
                    task_id = identifier(proposal.proposal_id)
                    path = (store.root / "tasks" / (task_id + ".json")).resolve()
                    if not path.is_relative_to(store.root) or not path.is_file():
                        raise ValueError("Task attachment is missing or outside private memory")
                    record = RuleRecord.model_validate_json(path.read_text(encoding="utf-8"))
                    if (
                        proposal.status.value not in {
                            "applied", "synced", "sync_pending", "sync_conflict",
                        }
                        or proposal_digest(proposal) != proposal.approved_hash
                        or proposal.proposal_hash != proposal.approved_hash
                        or digest(record) != digest(proposal.after)
                        or record.scope.levels != ["paper"]
                        or len(record.scope.paper_ids) != 1
                    ):
                        raise ValueError("Task does not match its approved paper proposal")
                except (OSError, ValueError) as exc:
                    raise HTTPException(
                        409, "A task record cannot be verified against its approval",
                    ) from exc
                records.append({
                    "task_id": task_id,
                    "proposal_id": proposal.proposal_id,
                    "proposal_hash": proposal.approved_hash,
                    "paper_id": record.scope.paper_ids[0],
                    "created_at": proposal.created_at,
                    "record": record,
                })
            return records
