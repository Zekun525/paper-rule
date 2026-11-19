import base64
import json

import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.persistence.store import MemoryStore
from paperrule.providers import AIResponse, OpenAIAPIProvider


def setup_feedback(tmp_path):
    root = tmp_path / "synthetic-memory"
    client = TestClient(create_app(root))
    imported = client.post("/api/sources", json={
        "filename": "synthetic-analysis.txt",
        "content_base64": base64.b64encode(b"Explain each synthetic inference.").decode(),
    })
    assert imported.status_code == 200
    return client, MemoryStore(root), imported.json()["feedback"][0]


def test_manual_analysis_is_unavailable_without_confirming_anything(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "manual")
    client, store, item = setup_feedback(tmp_path)
    response = client.post("/api/feedback/" + item["id"] + "/analyses",
                           json={"expected_sha256": item["sha256"]})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "unavailable"
    assert result["error"] == "provider_not_configured"
    assert result["classification_confirmed"] is False
    assert result["proposal_created"] is False
    assert result["suggestion"] is None
    assert store.feedback()[0].model_dump(mode="json") == item
    assert store.rules() == []
    assert store.proposals() == []
    assert store.decisions() == []


def test_ai_analysis_is_evidence_bound_and_persisted_as_a_suggestion(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    client, store, item = setup_feedback(tmp_path)
    calls = []

    def chat(self, messages, **kwargs):
        data = json.loads(messages[-1]["content"])
        calls.append(data)
        return AIResponse(text=json.dumps({
            "feedback_id": data["feedback"]["id"],
            "feedback_sha256": data["feedback"]["sha256"],
            "classification": "reusable_rule",
            "explanation": "Synthetic feedback requests explanation of reasoning.",
            "rule": {
                "short_title": "Synthetic clarity",
                "statement": "Explain the reasoning behind each synthetic inference.",
                "scope": {"levels": ["global"]},
            },
            "related_rules": [],
        }), provider="openai_api", model="synthetic-model")

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    url = "/api/feedback/" + item["id"] + "/analyses"
    response = client.post(url, json={"expected_sha256": item["sha256"]})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "suggested"
    assert result["stale"] is False
    assert result["suggestion"]["rule"]["source_feedback_ids"] == [item["id"]]
    assert result["suggestion"]["rule"]["status"] == "proposed"
    assert calls[0]["feedback"]["quote"] == item["quote"]
    assert client.get(url).json() == [result]
    assert store.feedback()[0].model_dump(mode="json") == item
    assert store.proposals() == []
    assert store.rules() == []
    assert store.decisions() == []


@pytest.mark.parametrize("failure", ["wrong-evidence", "one-off-rule", "invented-relation"])
def test_invalid_analysis_cannot_create_a_rule_or_confirm_classification(
    tmp_path, monkeypatch, failure,
):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    client, store, item = setup_feedback(tmp_path)

    def chat(self, messages, **kwargs):
        reply = {
            "feedback_id": item["id"], "feedback_sha256": item["sha256"],
            "classification": "reusable_rule", "explanation": "Synthetic explanation.",
            "rule": {"short_title": "Synthetic draft", "statement": "Explain synthetic reasoning.",
                     "scope": {"levels": ["global"]}},
            "related_rules": [],
        }
        if failure == "wrong-evidence":
            reply["feedback_sha256"] = "0" * 64
        elif failure == "one-off-rule":
            reply["classification"] = "one_off_edit"
        else:
            reply["related_rules"] = [{
                "rule_id": "R-SYNTHETIC-MISSING", "rule_version": 1,
                "relation": "extends", "reason": "Synthetic unsupported relation.",
            }]
        return AIResponse(text=json.dumps(reply), provider="openai_api", model="synthetic-model")

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    response = client.post("/api/feedback/" + item["id"] + "/analyses",
                           json={"expected_sha256": item["sha256"]})
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["error"] == "response_binding_invalid"
    assert response.json()["suggestion"] is None
    assert store.feedback()[0].model_dump(mode="json") == item
    assert store.rules() == []
    assert store.proposals() == []
    assert store.decisions() == []
