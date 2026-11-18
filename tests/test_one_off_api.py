import pytest
from fastapi.testclient import TestClient as RawTestClient
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.ingestion.pipeline import ingest_bytes
from paperrule.persistence.store import MemoryStore


@pytest.fixture
def task_proposal(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-task-memory")
    client = TestClient(create_app(store.root))
    store.save_paper(PaperProfile(paper_id="synthetic-task-paper"))
    _, items = ingest_bytes(
        b"Swap two synthetic paragraphs in this paper only.", "synthetic-task.txt",
        store, paper_id="synthetic-task-paper",
    )
    rule = RuleRecord(
        id="SYNTHETIC-TASK-RECORD", short_title="Swap two paragraphs",
        statement="Swap two synthetic paragraphs in this paper only.",
        source_feedback_ids=[items[0].id],
        scope=RuleScope(levels=["paper"], paper_ids=["synthetic-task-paper"]),
    )
    created = client.post("/api/proposals", json={
        "rule": rule.model_dump(mode="json"), "operation": "one_off",
    })
    assert created.status_code == 200, created.text
    return store, client, created.json()


def approve(client, proposal):
    response = client.post(
        "/api/proposals/" + proposal["proposal_id"] + "/approve",
        json={"proposal_hash": proposal["proposal_hash"]},
    )
    assert response.status_code == 200, response.text


def test_task_listing_requires_approval_and_preserves_its_identity(task_proposal):
    store, client, proposal = task_proposal
    assert client.get("/api/tasks").json() == []
    approve(client, proposal)
    response = client.get("/api/tasks")
    assert response.status_code == 200, response.text
    tasks = response.json()
    assert len(tasks) == 1
    assert tasks[0]["task_id"] == proposal["proposal_id"]
    assert tasks[0]["proposal_id"] == proposal["proposal_id"]
    assert tasks[0]["proposal_hash"] == proposal["proposal_hash"]
    assert tasks[0]["paper_id"] == "synthetic-task-paper"
    assert tasks[0]["record"] == proposal["after"]
    assert store.rules() == []
    approve(client, proposal)
    assert client.get("/api/tasks").json() == tasks


def test_tampered_task_is_not_presented_as_approved(task_proposal):
    store, client, proposal = task_proposal
    approve(client, proposal)
    changed = store.read_json("tasks")[0]
    changed["statement"] = "Different synthetic instruction without approval."
    store.write_json("tasks", proposal["proposal_id"], changed)
    response = client.get("/api/tasks")
    assert response.status_code == 409
    assert response.json() == {
        "detail": "A task record cannot be verified against its approval",
    }
    assert store.rules() == []


def test_unapproved_orphan_records_are_not_tasks(task_proposal):
    store, client, proposal = task_proposal
    store.write_json("tasks", "SYNTHETIC-ORPHAN", proposal["after"])
    assert client.get("/api/tasks").json() == []
    assert store.decision_count(proposal["proposal_id"]) == 0


def test_task_listing_requires_owner_access(task_proposal):
    store, _, _ = task_proposal
    client = RawTestClient(
        create_app(store.root), base_url="http://127.0.0.1",
        client=("127.0.0.1", 50000),
    )
    assert client.get("/api/tasks").status_code == 401
