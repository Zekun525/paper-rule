import hashlib
import json

import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import PaperProfile, ReviewReport, RuleRecord
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.review.files import check_documents


@pytest.fixture
def memory(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    profile = PaperProfile(paper_id="synthetic-snapshot-paper")
    store.save_paper(profile)
    governance = Governance(store)
    for rule_id, statement, method in (
        ("R-SYNTHETIC-SNAPSHOT", "avoid: obviously", "deterministic"),
        ("R-SYNTHETIC-SEMANTIC-SNAPSHOT", "Explain synthetic assumptions.", "semantic"),
    ):
        proposal = governance.propose(RuleRecord(
            id=rule_id, short_title="Synthetic snapshot guidance",
            statement=statement, check_method=method,
        ))
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
    return store, governance, profile


def document():
    text = "Synthetic obviously unsupported claim."
    return {
        "path": "synthetic.tex", "text": text,
        "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }


def test_check_persists_exportable_snapshot_and_truthful_coverage(memory):
    store, governance, profile = memory
    before_rules = store.rules()
    before_decisions = store.decisions()
    head = governance.git.head()
    payload = check_documents(store, [document()], profile, task="Synthetic snapshot review")
    report = ReviewReport.model_validate(payload)
    assert store.reviews() == [report]
    assert report.memory_commit == head
    assert report.memory_rules_dirty is False
    expected = hashlib.sha256(json.dumps(
        payload["rule_snapshot"], sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()
    assert report.rule_snapshot_sha256 == expected
    assert {rule.id for rule in report.rule_snapshot} == {rule.id for rule in before_rules}
    coverage = {item.rule_id: item for item in report.coverage}
    assert coverage["R-SYNTHETIC-SNAPSHOT"].status == "checked"
    assert coverage["R-SYNTHETIC-SNAPSHOT"].checked_line_count == 1
    assert coverage["R-SYNTHETIC-SEMANTIC-SNAPSHOT"].status == "unavailable"
    assert coverage["R-SYNTHETIC-SEMANTIC-SNAPSHOT"].checked_line_count == 0
    assert report.status == "incomplete"
    assert report.semantic_status == "not_reviewed"
    assert report.latex_build_status == "not_run"
    assert report.findings[0].location == "synthetic.tex:1"
    assert report.files[0].sha256 == document()["sha256"]
    assert store.rules() == before_rules
    assert store.decisions() == before_decisions
    assert governance.git.head() == head
    with TestClient(create_app(store.root)) as client:
        exported = client.get("/api/reviews/" + report.review_id + "/report")
        assert exported.status_code == 200
        assert exported.json() == payload
        markdown = client.get("/api/reviews/" + report.review_id + "/report?format=markdown")
        assert markdown.status_code == 200
        assert expected in markdown.text


def test_empty_diff_does_not_mark_any_rule_checked(memory):
    store, _governance, profile = memory
    report = ReviewReport.model_validate(check_documents(store, [], profile, diff_mode=True))
    assert report.status == "not_reviewed"
    assert report.coverage
    assert all(item.status == "not_reviewed" for item in report.coverage)
    assert all(item.checked_line_count == 0 for item in report.coverage)
    assert report.rule_snapshot
    assert report.files == []


def test_saved_snapshot_survives_later_rule_amendment(memory):
    store, governance, profile = memory
    payload = check_documents(store, [document()], profile)
    original = store.rule("R-SYNTHETIC-SNAPSHOT")
    proposal = governance.propose(
        original.model_copy(update={"statement": "avoid: clearly"}), "amend",
    )
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    assert store.rule(original.id).version == 2
    saved = store.reviews()[0]
    historical = next(rule for rule in saved.rule_snapshot if rule.id == original.id)
    assert historical.version == 1
    assert historical.statement == "avoid: obviously"
    assert saved.model_dump(mode="json") == payload
    assert saved.memory_commit != governance.git.head()


def test_uncommitted_rules_are_not_misrepresented_as_clean_commit(memory):
    store, governance, profile = memory
    head = governance.git.head()
    original = store.rule("R-SYNTHETIC-SNAPSHOT")
    store.save_rule(original.model_copy(update={"statement": "avoid: clearly"}))
    payload = check_documents(store, [document()], profile)
    assert payload["memory_commit"] == head
    assert payload["memory_rules_dirty"] is True
    snapshot = next(rule for rule in payload["rule_snapshot"] if rule["id"] == original.id)
    assert snapshot["statement"] == "avoid: clearly"
