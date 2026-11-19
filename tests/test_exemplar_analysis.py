"""Synthetic page-bound learning examples; scripted responses do not prove AI quality."""
import base64
import json

import pymupdf
import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.persistence.store import MemoryStore
from paperrule.providers import AIResponse, OpenAIAPIProvider
from paperrule.sync.git import GitSync

QUOTE = "Existing synthetic methods assume independent samples."
INTENT = "Learn how an introduction connects prior work to a research gap."


def import_exemplar(tmp_path, *, plain_text=False):
    root = tmp_path / "synthetic-exemplar-memory"
    client = TestClient(create_app(root))
    if plain_text:
        data = QUOTE.encode("utf-8")
        filename = "synthetic-exemplar.txt"
    else:
        with pymupdf.open() as pdf:
            first = pdf.new_page()
            first.insert_text((72, 72), "Synthetic abstract: a fictional demonstration.")
            second = pdf.new_page()
            second.insert_text((72, 72), chr(10).join([
                "Introduction", QUOTE,
                "This fictional study asks what changes when dependence is introduced.",
            ]))
            data = pdf.tobytes()
        filename = "synthetic-exemplar.pdf"
    response = client.post("/api/sources", json={
        "filename": filename, "content_base64": base64.b64encode(data).decode(),
        "kind": "exemplar", "intent": INTENT, "reviewer_id": "synthetic-author",
    })
    assert response.status_code == 200
    imported = response.json()
    item = next(row for row in imported["feedback"]
                if plain_text or row["location"]["page"] == 2)
    return client, MemoryStore(root), imported["source"], item, data


def reply_for(item):
    return {
        "feedback_id": item["id"], "feedback_sha256": item["sha256"],
        "classification": "exemplar",
        "explanation": "The synthetic introduction links a stated baseline to a limited gap.",
        "rule": None, "related_rules": [],
        "example": {
            "title": "Synthetic prior-work-to-gap transition", "focus": INTENT,
            "section": "introduction", "page": item["location"]["page"],
            "quote": QUOTE,
            "writing_feature": "State the baseline assumption before introducing the gap.",
            "adapted_example": "We first identify the fictional baseline, then state which assumption our illustrative setting changes.",
            "limitations": "This illustrates structure only; it is neither a verified research claim nor a universal writing rule.",
        },
    }


def snapshot(store):
    return (
        store.feedback(), store.sources(), store.rules(), store.proposals(), store.decisions(),
        GitSync(store.root).head() if (store.root / ".git").exists() else None,
        (store.root / ".git").exists(),
    )


def install_reply(monkeypatch, payload, calls):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def chat(self, messages, **kwargs):
        calls.append(json.loads(messages[-1]["content"]))
        return AIResponse(json.dumps(payload), "openai_api", "synthetic-exemplar-model")

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)


def test_pdf_learning_preserves_page_quote_intent_and_never_establishes_a_rule(tmp_path, monkeypatch):
    client, store, source, item, original = import_exemplar(tmp_path)
    baseline = snapshot(store)
    calls = []
    install_reply(monkeypatch, reply_for(item), calls)
    endpoint = "/api/feedback/" + item["id"] + "/analyses"
    response = client.post(endpoint, json={"expected_sha256": item["sha256"]})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "suggested"
    assert result["prompt_version"] == "feedback-analysis-v2"
    assert result["classification_confirmed"] is False
    assert result["proposal_created"] is False
    assert result["suggestion"]["rule"] is None
    example = result["suggestion"]["example"]
    assert example["page"] == 2 and example["quote"] == QUOTE
    assert example["source_location"]["page_index"] == 1
    assert example["source_id"] == source["id"]
    assert example["source_sha256"] == source["sha256"]
    assert example["feedback_id"] == item["id"]
    assert example["feedback_sha256"] == item["sha256"]
    assert example["human_review"] == "pending"
    assert example["mandatory_rule"] is False
    assert example["adapted_example"] not in item["quote"]
    assert calls[0]["source"]["intent"] == INTENT
    assert calls[0]["feedback"]["location"]["page"] == 2
    assert client.get(endpoint).json() == [result]
    assert (store.root / source["attachment"]).read_bytes() == original
    assert snapshot(store) == baseline
    preview = client.get("/api/sources/" + source["id"] + "/preview/1")
    assert preview.status_code == 200
    assert preview.content.startswith(bytes([137, 80, 78, 71]))


@pytest.mark.parametrize("failure", [
    "wrong-page", "invented-quote", "missing-example", "mandatory-rule",
    "different-class", "copied-example", "blank-limit", "invented-source",
])
def test_unbound_or_unsupported_examples_are_not_saved_as_valid_suggestions(
    tmp_path, monkeypatch, failure,
):
    client, store, source, item, original = import_exemplar(tmp_path)
    baseline = snapshot(store)
    payload = reply_for(item)
    if failure == "wrong-page":
        payload["example"]["page"] = 1
    elif failure == "invented-quote":
        payload["example"]["quote"] = "A fictional sentence absent from the source."
    elif failure == "missing-example":
        payload["example"] = None
    elif failure == "mandatory-rule":
        payload["rule"] = {
            "short_title": "Synthetic mandatory rule", "statement": "Always use this structure.",
            "scope": {"levels": ["global"]},
        }
    elif failure == "different-class":
        payload["classification"] = "research_fact"
    elif failure == "copied-example":
        payload["example"]["adapted_example"] = QUOTE
    elif failure == "blank-limit":
        payload["example"]["limitations"] = " "
    else:
        payload["example"]["source_id"] = "SRC-SYNTHETIC-INVENTED"
    calls = []
    install_reply(monkeypatch, payload, calls)
    response = client.post("/api/feedback/" + item["id"] + "/analyses",
                           json={"expected_sha256": item["sha256"]})
    assert response.status_code == 200
    assert response.json()["status"] == "unavailable"
    assert response.json()["suggestion"] is None
    assert response.json()["error"] in {"response_schema_invalid", "response_binding_invalid"}
    assert len(calls) == 1
    assert (store.root / source["attachment"]).read_bytes() == original
    assert snapshot(store) == baseline


def test_unclear_exemplar_can_request_clarification_without_inventing_an_example(tmp_path, monkeypatch):
    client, store, _source, item, _original = import_exemplar(tmp_path)
    baseline = snapshot(store)
    payload = reply_for(item)
    payload.update(classification="clarification_needed", example=None,
                   explanation="The intended comparison needs human clarification.")
    install_reply(monkeypatch, payload, [])
    response = client.post("/api/feedback/" + item["id"] + "/analyses",
                           json={"expected_sha256": item["sha256"]})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "suggested"
    assert result["suggestion"]["classification"] == "clarification_needed"
    assert result["suggestion"]["example"] is None
    assert result["suggestion"]["rule"] is None
    assert snapshot(store) == baseline


def test_text_exemplar_does_not_invent_pdf_pagination(tmp_path, monkeypatch):
    client, store, _source, item, _original = import_exemplar(tmp_path, plain_text=True)
    baseline = snapshot(store)
    install_reply(monkeypatch, reply_for(item), [])
    response = client.post("/api/feedback/" + item["id"] + "/analyses",
                           json={"expected_sha256": item["sha256"]})
    assert response.status_code == 200
    assert response.json()["status"] == "suggested"
    example = response.json()["suggestion"]["example"]
    assert example["page"] is None
    assert example["source_location"]["page_index"] is None
    assert snapshot(store) == baseline
