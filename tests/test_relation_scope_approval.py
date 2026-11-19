import pytest

from paperrule.domain.models import RuleRecord, RuleScope
from paperrule.governance.service import Governance, GovernanceError
from paperrule.persistence.store import MemoryStore


@pytest.mark.parametrize("relation_type", ["narrows", "exception_to"])
@pytest.mark.parametrize("parent_scope,child_scope,allowed", [
    ({}, {"paper_ids": ["synthetic-paper"]}, True),
    ({}, {}, False),
    ({"paper_ids": ["synthetic-a"]}, {"paper_ids": ["synthetic-b"]}, False),
    ({"paper_ids": ["synthetic-a"]}, {}, False),
    ({}, {"include": ["unknown:synthetic"]}, False),
    ({}, {"exceptions": ["Unresolved synthetic condition."]}, False),
    ({"paper_ids": ["synthetic-a", "synthetic-b"]},
     {"include": ["paper:synthetic-a"]}, True),
], ids=[
    "paper-subset", "equal-scope", "different-paper", "wider-scope",
    "unknown-selector", "unresolved-condition", "selector-subset",
])
def test_approved_scope_relation_requires_proven_strict_subset(
    tmp_path, relation_type, parent_scope, child_scope, allowed,
):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    parent = RuleRecord(
        id="R-SYNTHETIC-PARENT", short_title="Synthetic general rule",
        statement="State the synthetic assumptions.", scope=RuleScope(**parent_scope),
    )
    initial = governance.propose(parent)
    governance.approve(initial.proposal_id, initial.proposal_hash)
    child = RuleRecord(
        id="R-SYNTHETIC-CHILD", short_title="Synthetic local rule",
        statement="State the synthetic local assumption.", scope=RuleScope(**child_scope),
        relations=[{
            "type": relation_type, "target_id": parent.id, "status": "approved",
        }],
    )
    proposal = governance.propose(child)
    original_rules = store.rules()
    original_decisions = store.decisions()
    original_commit = governance.git.head()
    if allowed:
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
        assert store.rule(parent.id) == original_rules[0]
        assert store.rule(child.id).relations == proposal.after.relations
        assert set(child.relations[0]) == {"type", "target_id", "status"}
        assert len(store.decisions()) == len(original_decisions) + 1
    else:
        with pytest.raises(GovernanceError, match="provably stricter scope"):
            governance.approve(proposal.proposal_id, proposal.proposal_hash)
        assert store.rules() == original_rules
        assert store.decisions() == original_decisions
        assert governance.git.head() == original_commit
        assert store.proposal(proposal.proposal_id).approved_hash is None


@pytest.mark.parametrize("relation_type", ["narrows", "exception_to"])
def test_unconfirmed_relation_remains_a_candidate_without_scope_authority(tmp_path, relation_type):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    child = RuleRecord(
        id="R-SYNTHETIC-CANDIDATE", short_title="Synthetic candidate",
        statement="Discuss a possible synthetic relation.",
        relations=[{
            "type": relation_type, "target_id": "R-SYNTHETIC-FUTURE", "status": "candidate",
        }],
    )
    proposal = governance.propose(child)
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    assert store.rule(child.id).relations == child.relations
    assert store.rule("R-SYNTHETIC-FUTURE") is None
