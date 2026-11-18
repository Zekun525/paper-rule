from hashlib import sha256

import pymupdf
import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.ingestion.pipeline import ingest_bytes
from paperrule.persistence.store import MemoryStore
from paperrule.sync.git import GitSync


@pytest.fixture
def memory(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    GitSync(store.root).init()
    return store, TestClient(create_app(store.root))


def transcription():
    return {
        "request_id": "synthetic-request-1", "text": "Synthetic manually transcribed evidence.",
        "reason": "Synthetic PDF has no text layer.", "reviewer_role": "synthetic-reviewer",
        "classification": "clarification_needed", "page": 1,
    }


def blank_pdf(store):
    with pymupdf.open() as document:
        document.new_page()
        original = document.tobytes()
    source, items = ingest_bytes(original, "synthetic-scan.pdf", store,
                                 reviewer_id="synthetic-advisor", paper_id="synthetic-paper")
    assert items == []
    return source, original


def test_transcription_retains_source_and_does_not_approve_or_commit(memory):
    store, client = memory
    source, original = blank_pdf(store)
    baseline = GitSync(store.root).head()
    url = "/api/sources/" + source.id + "/transcriptions"
    response = client.post(url, json=transcription())
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["source_id"] == source.id
    assert item["source_kind"] == source.kind.value
    assert item["reviewer_id"] == "synthetic-advisor"
    assert item["paper_id"] == "synthetic-paper"
    assert item["location"]["page_index"] == 0
    assert item["extraction_method"] == "manual_transcription"
    assert item["extraction_details"]["source_sha256"] == sha256(original).hexdigest()
    assert client.post(url, json=transcription()).json() == item
    assert len(store.feedback()) == 1
    assert store.sources()[0] == source
    assert (store.root / source.attachment).read_bytes() == original
    assert store.rules() == [] and store.proposals() == [] and store.decisions() == []
    assert GitSync(store.root).head() == baseline
    conflict = {**transcription(), "text": "Different synthetic text."}
    assert client.post(url, json=conflict).status_code == 409


@pytest.mark.parametrize("patch,status", [
    ({"page": 0}, 422), ({"page": 2}, 400), ({"text": "  "}, 400),
    ({"reason": ""}, 422), ({"reviewer_role": " "}, 400),
    ({"classification": "invented"}, 422), ({"source_id": "another-source"}, 422),
])
def test_invalid_transcriptions_do_not_write(memory, patch, status):
    store, client = memory
    source, _ = blank_pdf(store)
    result = client.post("/api/sources/" + source.id + "/transcriptions",
                         json={**transcription(), **patch})
    assert result.status_code == status
    assert store.feedback() == []


def test_missing_or_modified_source_cannot_be_used_as_evidence(memory):
    store, client = memory
    assert client.post("/api/sources/SRC-missing/transcriptions",
                       json=transcription()).status_code == 404
    source, _ = blank_pdf(store)
    (store.root / source.attachment).write_bytes(b"Synthetic tampered attachment.")
    assert client.post("/api/sources/" + source.id + "/transcriptions",
                       json=transcription()).status_code == 400
    assert store.feedback() == []


def test_corrections_are_append_only_and_bound_to_previous_revision(memory):
    store, client = memory
    source, items = ingest_bytes(b"Synthetic original feedback.", "synthetic.txt", store)
    original = items[0]
    baseline = GitSync(store.root).head()
    url = "/api/feedback/" + original.id + "/corrections"
    body = {
        "request_id": "synthetic-correction-1", "expected_sha256": original.sha256,
        "text": "Synthetic corrected interpretation.", "reason": "Synthetic extraction clarification.",
        "classification": "one_off_edit",
    }
    response = client.post(url, json=body)
    assert response.status_code == 200
    corrected = response.json()
    assert corrected["quote"] == original.quote
    assert corrected["source_id"] == source.id
    assert corrected["classification"] == original.classification.value
    assert corrected["sha256"] != original.sha256
    assert corrected["corrections"][0]["previous_sha256"] == original.sha256
    assert corrected["corrections"][0]["classification"] == "one_off_edit"
    assert client.post(url, json=body).json() == corrected
    assert client.post(url, json={**body, "text": "Different."}).status_code == 409
    assert client.post(url, json={
        **body, "request_id": "synthetic-correction-2",
    }).status_code == 409
    second = client.post(url, json={
        **body, "request_id": "synthetic-correction-2",
        "expected_sha256": corrected["sha256"], "text": "Synthetic second clarification.",
    })
    assert second.status_code == 200
    assert second.json()["corrections"][:1] == corrected["corrections"]
    assert len(second.json()["corrections"]) == 2
    assert store.rules() == [] and store.decisions() == []
    assert GitSync(store.root).head() == baseline


def test_correction_rejects_missing_feedback_and_invalid_fields(memory):
    store, client = memory
    body = {"request_id": "synthetic-correction", "expected_sha256": "0" * 64,
            "text": "Synthetic correction.", "reason": "Synthetic reason."}
    assert client.post("/api/feedback/F-missing/corrections", json=body).status_code == 404
    _, items = ingest_bytes(b"Synthetic feedback.", "synthetic.txt", store)
    url = "/api/feedback/" + items[0].id + "/corrections"
    assert client.post(url, json={**body, "expected_sha256": "bad"}).status_code == 422
    assert client.post(url, json={**body, "quote": "overwrite original"}).status_code == 422
    assert store.feedback()[0].corrections == []
