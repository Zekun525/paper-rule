"""Workspace-bounded synthetic Git devices for the disposable browser server."""

from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore


def register_sync_fixture(app: FastAPI, memory: Path, fixture_root: Path, token: str) -> None:
    repository = Path(__file__).resolve().parents[1]
    allowed = (repository / ".test-tmp").resolve()
    if not allowed.is_relative_to(repository):
        raise ValueError("Synthetic fixture directory escapes the repository")
    if not all(path.resolve().is_relative_to(allowed) for path in (memory, fixture_root)):
        raise ValueError("Synthetic Git devices must stay in workspace test storage")
    if not memory.name.startswith("browser-memory-"):
        raise ValueError("A disposable browser memory is required")
    if not fixture_root.name.startswith("browser-sync-"):
        raise ValueError("A disposable browser sync directory is required")
    store = MemoryStore(memory)
    governance = Governance(store)
    state: dict[str, str] = {}

    def authorize(value: str) -> None:
        if not value or value != token:
            raise HTTPException(403, "Invalid synthetic fixture token")

    @app.post("/__e2e/sync-fixture")
    def prepare(x_test_token: str = Header(default="")):
        authorize(x_test_token)
        with store.locked(wait=5):
            governance.git.init()
            if state or "origin" in governance.git.run("remote").splitlines():
                raise HTTPException(409, "A synthetic remote is already configured")
            suffix = uuid4().hex
            devices = fixture_root / suffix
            devices.mkdir()
            remote = devices / "origin.git"
            second_path = devices / "device-b"
            rule_id = "R-SYNTHETIC-WINDOWS-SYNC-" + suffix
            paper_id = "SYNTHETIC-WINDOWS-SYNC-" + suffix
            store.save_paper(PaperProfile(paper_id=paper_id, title="Synthetic sync paper"))
            base_statement = "Explain the synthetic shared assumption."
            local_statement = "Explain the synthetic local assumption next to its use."
            remote_statement = (
                "Explain the synthetic remote assumption. "
                "Literal <script>globalThis.syntheticSyncExecuted=true</script>."
            )
            proposal = governance.propose(RuleRecord(
                id=rule_id, short_title="Synthetic Windows synchronized guidance",
                statement=base_statement,
                scope=RuleScope(
                    levels=["paper"], paper_ids=[paper_id], sections=["proof"],
                    exceptions=["Synthetic exception retained for comparison."],
                ),
            ))
            governance.approve(proposal.proposal_id, proposal.proposal_hash)
            base = governance.git.head()
            governance.git.run("init", "--bare", str(remote))
            state.update({"remote": str(remote), "rule_id": rule_id})
            governance.git.run("remote", "add", "origin", str(remote))
            if governance.git.push()["status"] != "synced":
                raise RuntimeError("Synthetic initial push failed")
            governance.git.run("clone", str(remote), str(second_path))
            second = MemoryStore(second_path)
            other = Governance(second)

            def revise(target: MemoryStore, owner: Governance, statement: str) -> None:
                current = target.rule(rule_id)
                if current is None:
                    raise RuntimeError("Synthetic rule is missing")
                changed = current.model_copy(update={"statement": statement}, deep=True)
                draft = owner.propose(changed, "amend")
                owner.approve(draft.proposal_id, draft.proposal_hash)

            revise(second, other, remote_statement)
            revise(store, governance, local_statement)
            return {
                "rule_id": rule_id, "paper_id": paper_id,
                "base_commit": base, "local_commit": governance.git.head(),
                "remote_commit": other.git.head(),
                "base_statement": base_statement, "local_statement": local_statement,
                "remote_statement": remote_statement,
            }

    app.router.routes.insert(0, app.router.routes.pop())

    @app.post("/__e2e/sync-fixture/cleanup")
    def cleanup(x_test_token: str = Header(default="")):
        authorize(x_test_token)
        with store.locked(wait=5):
            if not state:
                return {"status": "nothing_to_detach"}
            if "origin" in governance.git.run("remote").splitlines():
                current = governance.git.run("remote", "get-url", "origin")
                if Path(current).resolve() != Path(state["remote"]).resolve():
                    raise HTTPException(409, "Synthetic remote identity changed")
                governance.git.run("remote", "remove", "origin")
            state.clear()
            return {"status": "detached"}

    app.router.routes.insert(0, app.router.routes.pop())
