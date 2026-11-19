"""Owner API workflow with synthetic manuscript data and scripted provider output."""
from hashlib import sha256

import pytest
from fastapi.testclient import TestClient as RawTestClient
from owner_client import TestClient
from test_semantic_review_integration import SyntheticProvider
from test_semantic_review_integration import memory as synthetic_memory

from paperrule.api.app import create_app

memory = synthetic_memory


def request_body(profile, **changes):
    return {
        "paper_id": profile.paper_id, "filename": "synthetic.tex",
        "text": "Synthetic obviously unsupported claim.", **changes,
    }


def test_owner_can_check_pasted_text_and_export_persisted_report(memory):
    store, governance, profile = memory
    baseline = store.rules(), store.decisions(), governance.git.head()
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/reviews/check", json=request_body(profile))
        assert response.status_code == 200
        report = response.json()
        assert report["paper_id"] == profile.paper_id
        assert report["status"] == "incomplete"
        assert report["semantic_status"] == "not_reviewed"
        assert report["semantic_evidence"] == []
        assert report["findings"][0]["location"] == "synthetic.tex:1"
        expected = sha256(request_body(profile)["text"].encode("utf-8")).hexdigest()
        assert report["files"][0]["sha256"] == expected
        exported = client.get("/api/reviews/" + report["review_id"] + "/report")
        assert exported.status_code == 200
        assert exported.json() == report
    assert store.reviews()[0].model_dump(mode="json") == report
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


def test_semantic_request_without_explicit_consent_never_calls_provider(memory, monkeypatch):
    store, _governance, profile = memory
    provider = SyntheticProvider()
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    monkeypatch.setattr("paperrule.review.files.OpenAIAPIProvider", lambda: provider)
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/reviews/check", json=request_body(profile, semantic=True))
    assert response.status_code == 422
    assert provider.calls == []
    assert store.reviews() == []


def test_explicit_semantic_request_preserves_evidence_without_rule_changes(memory, monkeypatch):
    store, governance, profile = memory
    baseline = store.rules(), store.decisions(), governance.git.head()
    provider = SyntheticProvider("violation")
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    monkeypatch.setattr("paperrule.review.files.OpenAIAPIProvider", lambda: provider)
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/reviews/check", json=request_body(
            profile, semantic=True, send_to_provider=True, section="Proof", task="revise",
        ))
    assert response.status_code == 200
    report = response.json()
    assert len(provider.calls) == 1
    assert report["semantic_status"] == "reviewed"
    assert report["section"] == "Proof" and report["task"] == "revise"
    assert report["semantic_evidence"][0]["human_review"] == "pending"
    assert report["semantic_evidence"][0]["formal_proof_status"] == "not_performed"
    assert {finding["review_type"] for finding in report["findings"]} == {
        "deterministic", "semantic",
    }
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


def test_unconfigured_ai_keeps_deterministic_findings_and_incomplete_status(memory):
    store, _governance, profile = memory
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/reviews/check", json=request_body(
            profile, semantic=True, send_to_provider=True,
        ))
    assert response.status_code == 200
    report = response.json()
    assert report["status"] == "incomplete"
    assert report["semantic_status"] == "not_reviewed"
    assert len(report["findings"]) == 1
    assert report["semantic_evidence"][0]["error"] == "semantic_provider_unavailable"


@pytest.mark.parametrize("changes", [
    {"text": " "}, {"filename": "../private.tex"},
    {"filename": "C:" + chr(92) + "private.tex"},
    {"filename": "synthetic.py"}, {"max_semantic_calls": 33},
    {"semantic": "true"}, {"mode": "diff", "text": "unexpected text"},
], ids=["empty", "traversal", "absolute-path", "suffix", "budget", "bool", "mixed-input"])
def test_invalid_requests_do_not_save_reports(memory, changes):
    store, _governance, profile = memory
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/reviews/check", json=request_body(profile, **changes))
    assert response.status_code == 422
    assert store.reviews() == []


def test_diff_requires_saved_project_and_unknown_paper_is_rejected(memory):
    store, _governance, profile = memory
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/reviews/check", json=request_body(profile, mode="diff", text=""))
        assert response.status_code == 400
        response = client.post("/api/reviews/check", json=request_body(profile, paper_id="SYNTHETIC-MISSING"))
        assert response.status_code == 404
    assert store.reviews() == []


def test_unauthenticated_request_cannot_start_review(memory):
    store, _governance, profile = memory
    with RawTestClient(create_app(store.root), base_url="http://127.0.0.1",
                       client=("127.0.0.1", 50000)) as client:
        response = client.post("/api/reviews/check", json=request_body(profile))
    assert response.status_code == 401
    assert store.reviews() == []
