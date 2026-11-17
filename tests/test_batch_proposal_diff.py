from paperrule.domain.models import RuleRecord
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore


def test_batch_diff_includes_every_rule_and_preserves_active_records(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    for rule_id in ("R-SYNTHETIC-A", "R-SYNTHETIC-B"):
        proposal = governance.propose(RuleRecord(
            id=rule_id, short_title="Synthetic guidance",
            statement=f"Original synthetic instruction for {rule_id}.",
        ))
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
    before = store.rules()
    first, second = before
    proposal = governance.propose(
        first.model_copy(update={"statement": "Revised first synthetic instruction."}),
        "restore",
        additional=[second.model_copy(update={"statement": "Revised second synthetic instruction."})],
    )
    result = governance.diff(proposal)
    for rule in (first, second):
        assert f"--- {rule.id}/before" in result
        assert f"+++ {rule.id}/proposed" in result
        assert rule.statement in result
    assert "Revised first synthetic instruction." in result
    assert "Revised second synthetic instruction." in result
    assert store.rules() == before
