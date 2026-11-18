import pytest
from fastapi.testclient import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import PaperProfile, RuleRecord
from paperrule.governance.service import Governance, GovernanceError
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import build_context


def guidance(rule_id, relations=None):
    return RuleRecord(
        id=rule_id, short_title="Synthetic relation guidance",
        statement="State the synthetic assumption.", relations=relations or [],
    )


@pytest.fixture
def memory(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    target = governance.propose(guidance("R-SYNTHETIC-B"))
    governance.approve(target.proposal_id, target.proposal_hash)
    return store, governance


@pytest.mark.parametrize("relation,reason", [
    ({"type": "conflicts_with", "target_id": "R-SYNTHETIC-MISSING", "status": "approved"},
     "missing target"),
    ({"type": "conflicts_with", "target_id": "R-SYNTHETIC-A", "status": "approved"},
     "itself"),
    ({"type": "synthetic_unsupported", "target_id": "R-SYNTHETIC-B"},
     "not supported"),
    ({"type": "conflicts_with", "target_id": "R-SYNTHETIC-B", "status": "synthetic_invalid"},
     "status"),
    ({"type": "conflicts_with", "target_id": "../synthetic-outside"},
     "valid target identifier"),
])
def test_invalid_relation_cannot_change_authority_or_create_approval(memory, relation, reason):
    store, governance = memory
    proposal = governance.propose(guidance("R-SYNTHETIC-A", [relation]))
    before = store.rules()
    decisions = store.decisions()
    commit = governance.git.head()
    with pytest.raises(GovernanceError, match=reason):
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
    assert store.rules() == before
    assert store.decisions() == decisions
    assert governance.git.head() == commit
    assert store.proposal(proposal.proposal_id).approved_hash is None


def test_candidate_can_reference_a_not_yet_created_rule_without_becoming_authoritative(memory):
    store, governance = memory
    relation = {
        "type": "conflicts_with", "target_id": "R-SYNTHETIC-FUTURE", "status": "candidate",
    }
    proposal = governance.propose(guidance("R-SYNTHETIC-A", [relation]))
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    assert store.rule("R-SYNTHETIC-A").relations == [relation]
    bundle = build_context(store.rules(), PaperProfile(paper_id="synthetic-paper"))
    assert bundle["unresolved_conflicts"] == []
    assert bundle["relation_issues"] == []
    assert bundle["complete"] is True


def test_batch_can_approve_relations_between_its_new_rules_once(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    first = guidance("R-SYNTHETIC-A", [{
        "type": "conflicts_with", "target_id": "R-SYNTHETIC-B", "status": "approved",
    }])
    proposal = governance.propose(first, additional=[guidance("R-SYNTHETIC-B")])
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    head = governance.git.head()
    assert governance.approve(proposal.proposal_id, proposal.proposal_hash)[1] == "already-applied"
    assert governance.git.head() == head
    assert len(store.decisions()) == 1
    bundle = build_context(store.rules(), PaperProfile(paper_id="synthetic-paper"))
    assert bundle["complete"] is False
    assert bundle["unresolved_conflicts"][0]["rule_ids"] == [
        "R-SYNTHETIC-A", "R-SYNTHETIC-B",
    ]


def test_api_reports_invalid_approved_relation_without_activating_it(memory):
    store, governance = memory
    proposal = governance.propose(guidance("R-SYNTHETIC-A", [{
        "type": "conflicts_with", "target_id": "R-SYNTHETIC-MISSING", "status": "approved",
    }]))
    before = store.rules()
    with TestClient(create_app(store.root)) as client:
        result = client.post("/api/proposals/" + proposal.proposal_id + "/approve", json={
            "proposal_hash": proposal.proposal_hash,
        })
        assert result.status_code == 400
        assert "missing target" in result.json()["detail"]
    assert store.rules() == before
