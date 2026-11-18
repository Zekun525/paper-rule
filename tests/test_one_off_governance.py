import pytest

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.governance.service import Governance, GovernanceError
from paperrule.ingestion.corrections import CorrectionInput, append_correction
from paperrule.ingestion.pipeline import ingest_bytes
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import build_context


@pytest.fixture
def evidence(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.save_paper(PaperProfile(paper_id="synthetic-paper"))
    _, items = ingest_bytes(b"Swap these two synthetic paragraphs.", "synthetic.txt",
                            store, paper_id="synthetic-paper")
    return store, items[0]


def mark_one_off(store, item):
    return append_correction(store, item.id, CorrectionInput(
        request_id="synthetic-one-off", expected_sha256=item.sha256,
        text="Swap these two paragraphs in this paper only.",
        reason="Synthetic reviewer confirmed a local edit.", classification="one_off_edit",
    ))


def task_rule(item):
    return RuleRecord(
        id="SYNTHETIC-TASK", short_title="Swap paragraphs",
        statement="Swap the two synthetic paragraphs in this paper only.",
        source_feedback_ids=[item.id],
        scope=RuleScope(levels=["paper"], paper_ids=["synthetic-paper"]),
    )


def test_approved_task_is_persisted_without_becoming_a_rule(evidence):
    store, item = evidence
    mark_one_off(store, item)
    gov = Governance(store)
    proposal = gov.propose(task_rule(item), operation="one_off")
    assert store.read_json("tasks") == []
    approved, result = gov.approve(proposal.proposal_id, proposal.proposal_hash)
    assert result == "applied"
    assert store.rules() == []
    tasks = store.read_json("tasks")
    assert len(tasks) == 1
    assert tasks[0]["scope"]["paper_ids"] == ["synthetic-paper"]
    assert tasks[0]["source_feedback_ids"] == [item.id]
    context = build_context(store.rules(), PaperProfile(paper_id="synthetic-paper"),
                            "intro", "revise")
    assert context["rules"] == []
    assert gov.git.head() == approved.applied_commit
    assert store.decision_count(proposal.proposal_id) == 1
    assert gov.approve(proposal.proposal_id, proposal.proposal_hash)[1] == "already-applied"
    assert len(store.read_json("tasks")) == 1


def test_one_off_feedback_cannot_be_promoted_via_either_reference_field(evidence):
    store, item = evidence
    mark_one_off(store, item)
    gov = Governance(store)
    with pytest.raises(GovernanceError, match="One-off feedback"):
        gov.propose(task_rule(item))
    unlinked = task_rule(item).model_copy(update={"source_feedback_ids": []})
    with pytest.raises(GovernanceError, match="One-off feedback"):
        gov.propose(unlinked, feedback_ids=[item.id])
    assert store.rules() == [] and store.proposals() == []


def test_correction_after_drafting_is_rechecked_before_approval(evidence):
    store, item = evidence
    gov = Governance(store)
    proposal = gov.propose(task_rule(item))
    baseline = gov.git.head()
    mark_one_off(store, item)
    with pytest.raises(GovernanceError, match="One-off feedback"):
        gov.approve(proposal.proposal_id, proposal.proposal_hash)
    assert gov.git.head() == baseline
    assert store.rules() == [] and store.read_json("tasks") == []
    assert store.decision_count(proposal.proposal_id) == 0


@pytest.mark.parametrize("scope", [
    RuleScope(),
    RuleScope(levels=["paper"], paper_ids=[]),
    RuleScope(levels=["paper"], paper_ids=["synthetic-paper", "other-paper"]),
    RuleScope(levels=["paper"], paper_ids=["missing-paper"]),
])
def test_one_off_requires_one_existing_paper(evidence, scope):
    store, item = evidence
    with pytest.raises(GovernanceError):
        Governance(store).propose(task_rule(item).model_copy(update={"scope": scope}),
                                  operation="one_off")
    assert store.proposals() == [] and store.read_json("tasks") == []


def test_one_off_rejects_cross_paper_evidence_and_additional_rules(evidence):
    store, item = evidence
    store.save_paper(PaperProfile(paper_id="synthetic-other"))
    rule = task_rule(item)
    rule.scope.paper_ids = ["synthetic-other"]
    with pytest.raises(GovernanceError, match="different paper"):
        Governance(store).propose(rule, operation="one_off")
    extra = RuleRecord(id="SYNTHETIC-EXTRA", short_title="Extra", statement="Synthetic.")
    with pytest.raises(GovernanceError, match="exactly one task"):
        Governance(store).propose(task_rule(item), operation="one_off", additional=[extra])
    assert store.rules() == [] and store.proposals() == []
