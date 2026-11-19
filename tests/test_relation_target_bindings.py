import pytest

from paperrule.domain.models import RuleRecord, RuleScope
from paperrule.governance.relation_bindings import target_digest
from paperrule.governance.service import ConflictError, Governance, GovernanceError
from paperrule.persistence.store import MemoryStore, proposal_digest


def parent_rule():
    return RuleRecord(
        id="R-SYNTHETIC-PARENT", short_title="Synthetic parent",
        statement="State the synthetic assumptions.",
    )


def child_rule(relation_type="exception_to", target="R-SYNTHETIC-PARENT"):
    return RuleRecord(
        id="R-SYNTHETIC-CHILD", short_title="Synthetic local guidance",
        statement="State the synthetic local assumption.",
        scope=RuleScope(paper_ids=["synthetic-paper"]),
        relations=[{"type": relation_type, "target_id": target, "status": "approved"}],
    )


@pytest.fixture
def memory(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    proposal = governance.propose(parent_rule())
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    return store, governance


@pytest.mark.parametrize("kind", ["narrows", "exception_to", "supersedes"])
def test_target_pin_is_reviewable_and_hashed_before_approval(memory, kind):
    store, governance = memory
    child = child_rule(kind)
    original = child.model_dump(mode="json")
    proposal = governance.propose(child)
    target = store.rule("R-SYNTHETIC-PARENT")
    pin = proposal.after.relations[0]
    assert pin["target_version"] == str(target.version)
    assert pin["target_sha256"] == target_digest(target)
    assert child.model_dump(mode="json") == original
    assert store.proposal(proposal.proposal_id).after.relations == proposal.after.relations
    changed = proposal.model_copy(deep=True)
    changed.after.relations[0].pop("target_sha256")
    assert proposal_digest(changed) != proposal.proposal_hash
    reviewed_hash = proposal.proposal_hash
    governance.approve(proposal.proposal_id, reviewed_hash)
    assert store.rule(child.id).relations == proposal.after.relations
    assert store.proposal(proposal.proposal_id).approved_hash == reviewed_hash
    head = governance.git.head()
    assert governance.approve(proposal.proposal_id, reviewed_hash)[1] == "already-applied"
    assert governance.git.head() == head


@pytest.mark.parametrize("field,value", [
    ("target_version", "999"), ("target_sha256", "0" * 64),
])
def test_even_a_rehashed_proposal_cannot_approve_tampered_target_pins(memory, field, value):
    store, governance = memory
    proposal = governance.propose(child_rule())
    proposal.after.relations[0][field] = value
    store.save_proposal(proposal)
    before = store.rules(), store.decisions(), governance.git.head()
    with pytest.raises(GovernanceError, match="target binding"):
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
    assert (store.rules(), store.decisions(), governance.git.head()) == before
    assert store.proposal(proposal.proposal_id).approved_hash is None


def test_target_file_change_without_git_commit_cannot_reuse_an_old_binding(memory):
    store, governance = memory
    proposal = governance.propose(child_rule())
    changed = store.rule("R-SYNTHETIC-PARENT").model_copy(deep=True)
    changed.version += 1
    changed.statement = "Explain the revised synthetic assumption."
    store.save_rule(changed)
    before = store.rules(), store.decisions(), governance.git.head()
    with pytest.raises(GovernanceError, match="target binding"):
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
    assert (store.rules(), store.decisions(), governance.git.head()) == before


@pytest.mark.parametrize("existing_parent", [False, True])
def test_batch_binding_predicts_the_actual_approved_target_state(tmp_path, existing_parent):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    parent = parent_rule()
    if existing_parent:
        first = governance.propose(parent)
        governance.approve(first.proposal_id, first.proposal_hash)
        parent = store.rule(parent.id).model_copy(deep=True)
        parent.statement = "State the revised synthetic batch assumption."
    proposal = governance.propose(child_rule(), additional=[parent])
    pin = dict(proposal.after.relations[0])
    assert pin["target_version"] == ("2" if existing_parent else "1")
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    assert pin["target_sha256"] == target_digest(store.rule(parent.id))
    assert store.rule("R-SYNTHETIC-CHILD").relations[0] == pin


def test_cyclic_batch_remains_editable_but_cannot_be_approved(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    governance = Governance(store)
    first = child_rule("supersedes", "R-SYNTHETIC-SECOND")
    second = parent_rule()
    second.id = "R-SYNTHETIC-SECOND"
    second.relations = [{
        "type": "supersedes", "target_id": first.id, "status": "approved",
    }]
    proposal = governance.propose(first, additional=[second])
    assert "target_sha256" not in proposal.after.relations[0]
    before = store.rules(), store.decisions(), governance.git.head()
    with pytest.raises(GovernanceError, match="target binding"):
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
    assert (store.rules(), store.decisions(), governance.git.head()) == before


def test_discussion_rebinds_a_new_revision_without_bypassing_baseline_conflicts(memory):
    store, governance = memory
    proposal = governance.propose(child_rule())
    old_hash = proposal.proposal_hash
    parent = store.rule("R-SYNTHETIC-PARENT").model_copy(deep=True)
    parent.statement = "State the newly approved synthetic assumption."
    update = governance.propose(parent, "amend")
    governance.approve(update.proposal_id, update.proposal_hash)
    revised = governance.discuss(
        proposal.proposal_id, "Review the revised synthetic target.",
        revised=proposal.after.model_copy(deep=True),
    )
    assert revised.proposal_hash != old_hash
    assert revised.after.relations[0]["target_version"] == "2"
    assert revised.after.relations[0]["target_sha256"] == target_digest(store.rule(parent.id))
    with pytest.raises(ConflictError):
        governance.approve(revised.proposal_id, old_hash)
    with pytest.raises(ConflictError, match="baseline"):
        governance.approve(revised.proposal_id, revised.proposal_hash)
    assert store.rule("R-SYNTHETIC-CHILD") is None
