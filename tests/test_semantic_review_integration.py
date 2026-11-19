"""Synthetic provider integration checks; these do not establish model accuracy."""
import json
from hashlib import sha256

import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import PaperProfile, ReviewReport, RuleRecord, digest
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.providers import AIResponse, ProviderUnavailable
from paperrule.providers.base import AIProvider
from paperrule.review.files import check_documents


class SyntheticProvider(AIProvider):
    name = "synthetic-integration-provider"

    def __init__(self, mode="compliant"):
        self.mode = mode
        self.calls = []

    def chat(self, messages, *, timeout=30):
        self.calls.append(messages)
        if self.mode == "unavailable":
            raise ProviderUnavailable("Synthetic private diagnostic", code="network_error")
        if self.mode == "invalid":
            return AIResponse("not JSON", self.name, "synthetic-model")
        sent = json.loads(messages[-1]["content"])
        number = sent["selected_lines"][0]
        payload = {
            "rule_id": sent["rule"]["id"],
            "rule_version": sent["rule"]["version"],
            "verdict": self.mode,
            "explanation": "Synthetic judgment for integration testing only.",
            "findings": [],
            "unresolved": ["Synthetic context is insufficient."]
            if self.mode == "uncertain" else [],
        }
        if self.mode == "violation":
            payload["findings"] = [{
                "line": number, "quote": sent["excerpt"].splitlines()[number - 1],
                "explanation": "A synthetic assumption was omitted.",
                "recommendation": "State the synthetic assumption.",
            }]
        return AIResponse(json.dumps(payload), self.name, "synthetic-model")


@pytest.fixture
def memory(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "manual")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    profile = PaperProfile(paper_id="SYNTHETIC-INTEGRATION")
    store.save_paper(profile)
    governance = Governance(store)
    for rule_id, method, statement in (
        ("R-SYNTHETIC-PHRASE", "deterministic", "avoid: obviously"),
        ("R-SYNTHETIC-SEMANTIC", "semantic", "Explain synthetic assumptions."),
    ):
        proposal = governance.propose(RuleRecord(
            id=rule_id, short_title="Synthetic writing guidance",
            statement=statement, check_method=method,
        ))
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
    return store, governance, profile


def document(path="synthetic.tex", text="Synthetic obviously unsupported claim."):
    return {
        "path": path, "text": text,
        "sha256": sha256(text.encode("utf-8")).hexdigest(),
    }


def test_mixed_review_persists_bound_evidence_without_approval_or_rule_changes(memory):
    store, governance, profile = memory
    baseline = store.rules(), store.decisions(), governance.git.head()
    provider = SyntheticProvider()
    payload = check_documents(
        store, [document()], profile, semantic=True, semantic_provider=provider,
    )
    report = ReviewReport.model_validate(payload)
    assert report.status == "findings"
    assert report.semantic_status == "reviewed"
    assert all(item.status == "checked" for item in report.coverage)
    assert len(provider.calls) == 1
    assert len(report.semantic_evidence) == 1
    evidence = report.semantic_evidence[0]
    rule = store.rule(evidence.rule_id)
    assert evidence.rule_sha256 == digest(rule)
    assert evidence.file_sha256 == document()["sha256"]
    assert evidence.input_sha256 == document()["sha256"]
    assert evidence.selection["line_numbers"] == [1]
    assert evidence.human_review == "pending"
    assert evidence.formal_proof_status == "not_performed"
    assert report.memory_commit == baseline[2]
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline
    restarted = MemoryStore(store.root)
    assert restarted.reviews()[0].model_dump(mode="json") == payload
    with TestClient(create_app(store.root)) as client:
        exported = client.get("/api/reviews/" + report.review_id + "/report")
        assert exported.status_code == 200
        assert exported.json() == payload
        markdown = client.get("/api/reviews/" + report.review_id + "/report?format=markdown")
        assert markdown.status_code == 200
        assert evidence.rule_sha256 in markdown.text


@pytest.mark.parametrize("mode", ["unavailable", "invalid", "uncertain", "unconfigured"])
def test_incomplete_semantic_work_never_claims_checked_coverage(memory, mode):
    store, governance, profile = memory
    baseline = store.rules(), store.decisions(), governance.git.head()
    provider = None if mode == "unconfigured" else SyntheticProvider(mode)
    report = ReviewReport.model_validate(check_documents(
        store, [document()], profile, semantic=True, semantic_provider=provider,
    ))
    coverage = next(item for item in report.coverage if item.rule_id == "R-SYNTHETIC-SEMANTIC")
    assert coverage.status == "unavailable"
    assert coverage.checked_line_count == 0
    assert report.semantic_status == "not_reviewed"
    assert report.status == "incomplete"
    assert report.semantic_evidence[0].checked_line_count == 0
    assert "Synthetic private diagnostic" not in report.model_dump_json()
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


def test_call_budget_records_unreviewed_file_and_incomplete_rule(memory):
    store, _governance, profile = memory
    provider = SyntheticProvider()
    report = ReviewReport.model_validate(check_documents(
        store, [document(), document("synthetic-second.tex")], profile,
        semantic=True, semantic_provider=provider, max_semantic_calls=1,
    ))
    assert len(provider.calls) == 1
    assert len(report.semantic_evidence) == 2
    assert report.semantic_evidence[0].status == "checked"
    assert report.semantic_evidence[1].error == "semantic_call_budget_exceeded"
    assert report.semantic_evidence[1].checked_line_count == 0
    coverage = next(item for item in report.coverage if item.rule_id == "R-SYNTHETIC-SEMANTIC")
    assert coverage.status == "unavailable"
    assert coverage.checked_line_count == 0
    assert report.semantic_status == "incomplete"
    assert report.status == "incomplete"


def test_diff_review_preserves_changed_line_selection_and_findings(memory):
    store, _governance, profile = memory
    text = chr(10).join(["Synthetic context.", "Synthetic obviously unsupported claim."])
    manuscript = document(text=text)
    manuscript["changed_lines"] = {2}
    provider = SyntheticProvider("violation")
    report = ReviewReport.model_validate(check_documents(
        store, [manuscript], profile, diff_mode=True,
        semantic=True, semantic_provider=provider,
    ))
    assert report.status == "findings"
    assert all(item.checked_line_count == 1 for item in report.coverage)
    assert len(report.findings) == 2
    assert {item.review_type for item in report.findings} == {"deterministic", "semantic"}
    assert all(item.location == "synthetic.tex:2" for item in report.findings)
    assert all(item.confirmed is None for item in report.findings)
    assert report.semantic_evidence[0].selection == {
        "mode": "changed_lines", "line_numbers": [2],
    }
    assert json.loads(provider.calls[0][-1]["content"])["selected_lines"] == [2]


def test_empty_diff_does_not_contact_provider_or_claim_coverage(memory):
    store, _governance, profile = memory
    provider = SyntheticProvider()
    report = ReviewReport.model_validate(check_documents(
        store, [], profile, diff_mode=True, semantic=True, semantic_provider=provider,
    ))
    assert provider.calls == []
    assert report.status == "not_reviewed"
    assert report.semantic_status == "not_reviewed"
    assert report.semantic_evidence == []
    assert all(item.status == "not_reviewed" for item in report.coverage)


def test_phrase_exception_requires_semantic_judgment_and_can_clear_literal_hit(memory):
    store, governance, profile = memory
    original = store.rule("R-SYNTHETIC-PHRASE")
    scope = original.scope.model_copy(update={
        "exceptions": ["Quoted synthetic counterexamples may retain the phrase."],
    })
    proposal = governance.propose(original.model_copy(update={"scope": scope}), "amend")
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    baseline = store.rules(), store.decisions(), governance.git.head()
    manual = ReviewReport.model_validate(check_documents(store, [document()], profile))
    assert manual.findings == []
    phrase = next(item for item in manual.coverage if item.rule_id == original.id)
    assert phrase.status == "unavailable"
    assert phrase.reason == "semantic_exception_not_reviewed"
    provider = SyntheticProvider()
    reviewed = ReviewReport.model_validate(check_documents(
        store, [document()], profile, semantic=True, semantic_provider=provider,
    ))
    assert len(provider.calls) == 2
    assert reviewed.findings == []
    assert reviewed.status == "checked"
    assert reviewed.semantic_status == "reviewed"
    assert all(item.status == "checked" for item in reviewed.coverage)
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


@pytest.mark.parametrize("limit", [0, 33])
def test_invalid_request_budget_is_rejected_without_provider_call_or_report(memory, limit):
    store, _governance, profile = memory
    provider = SyntheticProvider()
    with pytest.raises(ValueError, match="request limit"):
        check_documents(store, [document()], profile, semantic=True,
                        semantic_provider=provider, max_semantic_calls=limit)
    assert provider.calls == []
    assert store.reviews() == []
