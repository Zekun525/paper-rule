"""Analysis history and concurrent responses bind the exact source and paper context."""
import base64
import json

from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import PaperProfile, digest
from paperrule.persistence.store import MemoryStore
from paperrule.providers import AIResponse, OpenAIAPIProvider


def setup_context(tmp_path, monkeypatch, *, during_request=None):
    store = MemoryStore(tmp_path / "synthetic-context-memory")
    client = TestClient(create_app(store.root))
    profile = PaperProfile(paper_id="SYNTHETIC-CONTEXT", venue="SYNTHETIC-A")
    assert client.post("/api/papers", json=profile.model_dump(mode="json")).status_code == 200
    imported = client.post("/api/sources", json={
        "filename": "synthetic-context.txt", "paper_id": profile.paper_id,
        "content_base64": base64.b64encode(b"Explain the synthetic assumptions.").decode(),
        "intent": "Synthetic original source intent.",
    })
    assert imported.status_code == 200
    source = imported.json()["source"]
    item = imported.json()["feedback"][0]
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def chat(self, messages, **kwargs):
        evidence = json.loads(messages[-1]["content"])["feedback"]
        if during_request:
            during_request(store, profile)
        return AIResponse(json.dumps({
            "feedback_id": evidence["id"], "feedback_sha256": evidence["sha256"],
            "classification": "reusable_rule", "explanation": "Synthetic reasoning guidance.",
            "rule": {
                "short_title": "Synthetic assumption clarity",
                "statement": "Explain the assumptions before using the synthetic inference.",
                "scope": {"levels": ["global"]},
            },
            "related_rules": [],
        }), "openai_api", "synthetic-context-model")

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    return client, store, profile, source, item


def analyze(client, item):
    endpoint = "/api/feedback/" + item["id"] + "/analyses"
    response = client.post(endpoint, json={"expected_sha256": item["sha256"]})
    return endpoint, response


def test_later_paper_profile_change_marks_history_stale_without_rewriting_it(tmp_path, monkeypatch):
    client, store, profile, source, item = setup_context(tmp_path, monkeypatch)
    endpoint, response = analyze(client, item)
    assert response.status_code == 200
    original = response.json()
    assert original["status"] == "suggested" and original["stale"] is False
    assert original["paper_profile_sha256"] == digest(profile)
    original_source = next(row for row in store.sources() if row.id == source["id"])
    assert original["source_record_sha256"] == digest(original_source)
    with store.locked():
        store.save_paper(profile.model_copy(update={"venue": "SYNTHETIC-B"}))
    history = client.get(endpoint).json()
    assert history[0]["stale"] is True
    assert history[0]["suggestion"] == original["suggestion"]
    stored = store.read_json("analyses")
    assert stored[0]["paper_profile_sha256"] == digest(profile)
    assert stored[0]["suggestion"] == original["suggestion"]
    assert store.rules() == [] and store.proposals() == [] and store.decisions() == []


def test_source_intent_change_marks_suggestions_stale_even_with_same_file_hash(tmp_path, monkeypatch):
    client, store, _profile, source, item = setup_context(tmp_path, monkeypatch)
    endpoint, response = analyze(client, item)
    assert response.status_code == 200
    original = response.json()
    with store.locked():
        current = next(row for row in store.sources() if row.id == source["id"])
        store.save_source(current.model_copy(update={"intent": "Synthetic revised learning intent."}))
    assert store.sources()[0].sha256 == source["sha256"]
    history = client.get(endpoint).json()
    assert history[0]["stale"] is True
    assert history[0]["source_record_sha256"] == original["source_record_sha256"]
    assert history[0]["suggestion"] == original["suggestion"]
    assert store.feedback()[0].model_dump(mode="json") == item
    assert store.rules() == [] and store.proposals() == [] and store.decisions() == []


def test_profile_change_during_request_rejects_obsolete_analysis_before_persistence(tmp_path, monkeypatch):
    def change_profile(store, profile):
        with store.locked():
            store.save_paper(profile.model_copy(update={"venue": "SYNTHETIC-B"}))

    client, store, _profile, _source, item = setup_context(
        tmp_path, monkeypatch, during_request=change_profile,
    )
    _endpoint, response = analyze(client, item)
    assert response.status_code == 409
    assert store.read_json("analyses") == []
    assert store.feedback()[0].model_dump(mode="json") == item
    assert store.rules() == [] and store.proposals() == [] and store.decisions() == []


def test_legacy_records_without_context_hashes_remain_readable_but_stale(tmp_path, monkeypatch):
    client, store, _profile, _source, item = setup_context(tmp_path, monkeypatch)
    endpoint, response = analyze(client, item)
    assert response.status_code == 200
    original = response.json()
    legacy = store.read_json("analyses")[0]
    legacy.pop("paper_profile_sha256")
    legacy.pop("source_record_sha256")
    with store.locked():
        store.write_json("analyses", legacy["analysis_id"], legacy)
    history = client.get(endpoint)
    assert history.status_code == 200
    assert history.json()[0]["stale"] is True
    assert history.json()[0]["suggestion"] == original["suggestion"]
    assert store.read_json("analyses") == [legacy]


def test_unrelated_paper_change_does_not_invalidate_the_bound_profile(tmp_path, monkeypatch):
    client, store, _profile, _source, item = setup_context(tmp_path, monkeypatch)
    endpoint, response = analyze(client, item)
    assert response.status_code == 200
    original = response.json()
    with store.locked():
        store.save_paper(PaperProfile(paper_id="SYNTHETIC-OTHER", venue="SYNTHETIC-C"))
    assert client.get(endpoint).json() == [original]
