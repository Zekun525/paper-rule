import pytest

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import build_context


def approved_pair(tmp_path, kind="exception_to", state="approved"):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    parent = RuleRecord(
        id="R-SYNTHETIC-GENERAL", short_title="Synthetic general guidance",
        statement="State the synthetic assumption before the claim.",
    )
    proposal = governance.propose(parent)
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    child = RuleRecord(
        id="R-SYNTHETIC-LOCAL", short_title="Synthetic local guidance",
        statement="Explain the synthetic local assumption next to its application.",
        scope=RuleScope(paper_ids=["synthetic-a"]),
        relations=[{"type": kind, "target_id": parent.id, "status": state}],
    )
    proposal = governance.propose(child)
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    return store, governance


@pytest.mark.parametrize("kind", ["narrows", "exception_to", "supersedes"])
def test_context_resolves_only_the_explicitly_approved_local_relationship(tmp_path, kind):
    store, governance = approved_pair(tmp_path, kind)
    before = store.rules(), store.decisions(), governance.git.head()
    bundle = build_context(store.rules(), PaperProfile(paper_id="synthetic-a"))
    assert [entry["rule"]["id"] for entry in bundle["rules"]] == ["R-SYNTHETIC-LOCAL"]
    assert bundle["complete"] is True
    assert bundle["relation_issues"] == []
    exclusion = next(entry for entry in bundle["excluded_rules"]
                     if entry["rule_id"] == "R-SYNTHETIC-GENERAL")
    assert exclusion["reason"] == "approved_" + kind
    assert exclusion["by_rule_id"] == "R-SYNTHETIC-LOCAL"
    assert bundle["approved_relations"][0]["target_version"] == 1
    other = build_context(store.rules(), PaperProfile(paper_id="synthetic-b"))
    assert [entry["rule"]["id"] for entry in other["rules"]] == ["R-SYNTHETIC-GENERAL"]
    assert other["approved_relations"] == []
    assert other["complete"] is True
    assert (store.rules(), store.decisions(), governance.git.head()) == before


def test_a_budget_omitted_replacement_cannot_make_context_look_complete(tmp_path):
    store, governance = approved_pair(tmp_path)
    before = store.rules(), governance.git.head()
    bundle = build_context(
        store.rules(), PaperProfile(paper_id="synthetic-a"), max_rule_chars=2,
    )
    assert bundle["rules"] == []
    assert bundle["complete"] is False
    assert bundle["mandatory_omitted"] == ["R-SYNTHETIC-LOCAL"]
    assert any(entry["rule_id"] == "R-SYNTHETIC-GENERAL"
               and entry["reason"] == "approved_exception_to"
               for entry in bundle["excluded_rules"])
    assert (store.rules(), governance.git.head()) == before


def test_newly_approved_target_version_invalidates_an_old_override(tmp_path):
    store, governance = approved_pair(tmp_path)
    parent = store.rule("R-SYNTHETIC-GENERAL").model_copy(deep=True)
    parent.statement = "Explain the revised synthetic general assumption."
    proposal = governance.propose(parent, "amend")
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    before = store.rules(), store.decisions(), governance.git.head()
    bundle = build_context(store.rules(), PaperProfile(paper_id="synthetic-a"))
    assert {entry["rule"]["id"] for entry in bundle["rules"]} == {
        "R-SYNTHETIC-GENERAL", "R-SYNTHETIC-LOCAL",
    }
    assert bundle["complete"] is False
    assert bundle["approved_relations"] == []
    assert bundle["relation_issues"] == [{
        "rule_id": "R-SYNTHETIC-LOCAL", "target_id": "R-SYNTHETIC-GENERAL",
        "reason": "override_target_binding_stale",
    }]
    assert (store.rules(), store.decisions(), governance.git.head()) == before


def test_candidate_relationship_does_not_change_context_selection(tmp_path):
    store, _ = approved_pair(tmp_path, state="candidate")
    bundle = build_context(store.rules(), PaperProfile(paper_id="synthetic-a"))
    assert len(bundle["rules"]) == 2
    assert bundle["approved_relations"] == []
    assert bundle["relation_issues"] == []
    assert bundle["complete"] is True
