import base64
import json

from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.ingestion.corrections import CorrectionInput, append_correction
from paperrule.persistence.store import MemoryStore
from paperrule.providers import AIResponse, OpenAIAPIProvider


def synthetic_feedback(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    client = TestClient(create_app(store.root))
    response = client.post("/api/sources", json={
        "filename": "synthetic-binding.txt",
        "content_base64": base64.b64encode(b"Explain the synthetic assumption.").decode(),
    })
    assert response.status_code == 200
    item = response.json()["feedback"][0]
    return client, store, item


def test_stale_feedback_is_rejected_before_requesting_a_model(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    client, store, item = synthetic_feedback(tmp_path)
    calls = []

    def unexpected_request(*args, **kwargs):
        calls.append(True)
        raise AssertionError("Stale evidence must not reach the model")

    monkeypatch.setattr(OpenAIAPIProvider, "chat", unexpected_request)
    response = client.post("/api/feedback/" + item["id"] + "/analyses",
                           json={"expected_sha256": "0" * 64})
    assert response.status_code == 409
    assert calls == []
    assert store.read_json("analyses") == []
    assert store.proposals() == []
    assert store.rules() == []
    assert store.decisions() == []
    assert store.feedback()[0].model_dump(mode="json") == item


def test_concurrent_feedback_correction_cannot_save_an_old_ai_suggestion(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    client, store, item = synthetic_feedback(tmp_path)

    def chat(self, messages, **kwargs):
        append_correction(store, item["id"], CorrectionInput(
            request_id="synthetic-concurrent-correction",
            expected_sha256=item["sha256"],
            text="This synthetic instruction applies only to the current example.",
            reason="Synthetic correction made while analysis was running.",
            classification="one_off_edit",
        ))
        return AIResponse(text=json.dumps({
            "feedback_id": item["id"],
            "feedback_sha256": item["sha256"],
            "classification": "reusable_rule",
            "explanation": "Synthetic obsolete interpretation.",
            "rule": {
                "short_title": "Synthetic obsolete draft",
                "statement": "Always explain the synthetic assumption.",
                "scope": {"levels": ["global"]},
            },
            "related_rules": [],
        }), provider="openai_api", model="synthetic-model")

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    response = client.post("/api/feedback/" + item["id"] + "/analyses",
                           json={"expected_sha256": item["sha256"]})
    assert response.status_code == 409
    assert store.read_json("analyses") == []
    updated = store.feedback()[0]
    assert updated.quote == item["quote"]
    assert updated.sha256 != item["sha256"]
    assert updated.corrections[-1]["classification"] == "one_off_edit"
    assert store.proposals() == []
    assert store.rules() == []
    assert store.decisions() == []


def test_analysis_history_marks_records_stale_after_a_feedback_correction(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "manual")
    client, store, item = synthetic_feedback(tmp_path)
    endpoint = "/api/feedback/" + item["id"] + "/analyses"
    response = client.post(endpoint, json={"expected_sha256": item["sha256"]})
    assert response.status_code == 200
    original = response.json()
    assert original["stale"] is False
    correction = client.post("/api/feedback/" + item["id"] + "/corrections", json={
        "request_id": "synthetic-later-correction",
        "expected_sha256": item["sha256"],
        "text": "Explain only the assumption used in this synthetic example.",
        "reason": "Synthetic later clarification.",
    })
    assert correction.status_code == 200
    history = client.get(endpoint)
    assert history.status_code == 200
    rows = history.json()
    assert len(rows) == 1
    assert rows[0]["analysis_id"] == original["analysis_id"]
    assert rows[0]["feedback_sha256"] == item["sha256"]
    assert rows[0]["stale"] is True
    stored = store.read_json("analyses")
    assert len(stored) == 1
    assert stored[0]["feedback_sha256"] == item["sha256"]
    assert store.proposals() == []
    assert store.rules() == []
    assert store.decisions() == []
