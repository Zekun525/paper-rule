from hashlib import sha256

import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.providers.base import AIProvider
from paperrule.review.files import check_documents


class NeverCallProvider(AIProvider):
    name = "synthetic-never-call"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, *, timeout=30):
        self.calls += 1
        raise AssertionError("Unresolved relationships must not contact a provider")


def prepare(tmp_path, method="deterministic", state="approved", conflict=False):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    first = PaperProfile(paper_id="synthetic-a")
    other = PaperProfile(paper_id="synthetic-b")
    store.save_paper(first)
    store.save_paper(other)
    governance = Governance(store)
    parent = RuleRecord(
        id="R-SYNTHETIC-PARENT", short_title="Synthetic parent",
        statement="avoid: synthetic old phrase", check_method=method,
        scope=RuleScope(paper_ids=[first.paper_id, other.paper_id]),
    )
    proposal = governance.propose(parent)
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    relations = [{"type": "exception_to", "target_id": parent.id, "status": state}]
    if conflict:
        relations.append({
            "type": "conflicts_with", "target_id": parent.id, "status": "approved",
        })
    child = RuleRecord(
        id="R-SYNTHETIC-CHILD", short_title="Synthetic local guidance",
        statement="avoid: synthetic new phrase", check_method=method,
        scope=RuleScope(paper_ids=[first.paper_id]), relations=relations,
    )
    proposal = governance.propose(child)
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    return store, governance, first, other


def manuscript():
    text = "synthetic old phrase and synthetic new phrase"
    return {"path": "synthetic.tex", "text": text,
            "sha256": sha256(text.encode("utf-8")).hexdigest()}


def test_review_uses_the_local_override_and_exports_its_selection_basis(tmp_path):
    store, governance, first, other = prepare(tmp_path)
    baseline = store.rules(), store.decisions(), governance.git.head()
    local = check_documents(store, [manuscript()], first)
    assert {row["rule_id"] for row in local["findings"]} == {"R-SYNTHETIC-CHILD"}
    assert [row["id"] for row in local["rule_snapshot"]] == ["R-SYNTHETIC-CHILD"]
    assert local["status"] == "findings"
    assert local["unavailable"] == local["unresolved"] == []
    assert len(local["selection_notes"]) == 1
    assert "R-SYNTHETIC-PARENT" in local["selection_notes"][0]
    assert "R-SYNTHETIC-CHILD" in local["selection_notes"][0]
    elsewhere = check_documents(store, [manuscript()], other)
    assert {row["rule_id"] for row in elsewhere["findings"]} == {"R-SYNTHETIC-PARENT"}
    assert elsewhere["selection_notes"] == []
    restored = next(report for report in MemoryStore(store.root).reviews()
                    if report.review_id == local["review_id"])
    assert restored.model_dump(mode="json") == local
    with TestClient(create_app(store.root)) as client:
        exported = client.get("/api/reviews/" + local["review_id"] + "/report")
        assert exported.status_code == 200
        assert exported.json()["selection_notes"] == local["selection_notes"]
        markdown = client.get(
            "/api/reviews/" + local["review_id"] + "/report?format=markdown",
        )
        assert markdown.status_code == 200
        assert "selection_notes" in markdown.text
        assert "R-SYNTHETIC-PARENT" in markdown.text
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


@pytest.mark.parametrize("semantic", [False, True])
def test_stale_relationship_blocks_both_checks_without_false_findings_or_model_calls(
    tmp_path, semantic,
):
    store, governance, first, _ = prepare(
        tmp_path, method="semantic" if semantic else "deterministic",
    )
    parent = store.rule("R-SYNTHETIC-PARENT").model_copy(deep=True)
    parent.statement = "avoid: synthetic revised phrase"
    proposal = governance.propose(parent, "amend")
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    baseline = store.rules(), store.decisions(), governance.git.head()
    provider = NeverCallProvider()
    report = check_documents(
        store, [manuscript()], first, semantic=semantic, semantic_provider=provider,
    )
    assert provider.calls == 0
    assert report["findings"] == []
    assert report["status"] in {"incomplete", "not_reviewed"}
    assert all(row["status"] == "unavailable" and row["checked_line_count"] == 0
               for row in report["coverage"])
    assert {row["reason"] for row in report["unavailable"]} == {"rule_relation_unresolved"}
    assert any("override_target_binding_stale" in note for note in report["unresolved"])
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


def test_candidate_relationship_does_not_remove_either_review_rule(tmp_path):
    store, _, first, _ = prepare(tmp_path, state="candidate")
    report = check_documents(store, [manuscript()], first)
    assert {row["rule_id"] for row in report["findings"]} == {
        "R-SYNTHETIC-PARENT", "R-SYNTHETIC-CHILD",
    }
    assert report["selection_notes"] == report["unresolved"] == []


def test_declared_conflict_cannot_be_hidden_by_a_review_override(tmp_path):
    store, _, first, _ = prepare(tmp_path, conflict=True)
    report = check_documents(store, [manuscript()], first)
    assert report["findings"] == []
    assert report["selection_notes"] == []
    assert report["status"] == "incomplete"
    assert {row["reason"] for row in report["unavailable"]} == {"rule_conflict_unresolved"}
