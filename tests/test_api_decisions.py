import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.persistence.store import MemoryStore


def propose(client):
    response = client.post("/api/proposals", json={
        "rule": {
            "id": "R-SYNTHETIC",
            "short_title": "Explain assumptions",
            "statement": "State the assumptions used in each implication.",
        },
    })
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize("action,status", [("reject", "rejected"), ("defer", "deferred")])
def test_decision_preserves_reason_and_evidence_without_activating_rules(tmp_path, action, status):
    memory = tmp_path / "memory"
    client = TestClient(create_app(memory))
    proposal = propose(client)
    reason = "Synthetic review: scope requires clarification."
    response = client.post(
        f"/api/proposals/{proposal['proposal_id']}/{action}",
        json={"reason": reason},
    )
    assert response.status_code == 200
    assert response.json()["status"] == status
    assert response.json()["decision_reason"] == reason
    assert client.get("/api/rules").json() == []
    reopened = MemoryStore(memory)
    events = reopened.decisions()
    assert len(events) == 1
    assert events[0].action == action
    assert events[0].reason == reason
    assert events[0].proposal_id == proposal["proposal_id"]
    assert events[0].proposal_hash == proposal["proposal_hash"]
    assert events[0].revision == proposal["revision"]
    assert reopened.proposal(proposal["proposal_id"]).decision_reason == reason


@pytest.mark.parametrize("action", ["reject", "defer"])
def test_decision_on_rejected_proposal_returns_conflict_without_extra_event(tmp_path, action):
    memory = tmp_path / "memory"
    client = TestClient(create_app(memory))
    proposal = propose(client)
    url = f"/api/proposals/{proposal['proposal_id']}"
    assert client.post(url + "/reject", json={"reason": "Synthetic rejection"}).status_code == 200
    assert client.post(url + "/" + action, json={"reason": "Must not overwrite"}).status_code == 409
    assert len(MemoryStore(memory).decisions()) == 1
    assert MemoryStore(memory).proposal(proposal["proposal_id"]).decision_reason == "Synthetic rejection"


@pytest.mark.parametrize("action", ["reject", "defer"])
def test_missing_proposal_is_not_reported_as_a_server_failure(tmp_path, action):
    client = TestClient(create_app(tmp_path / "memory"))
    assert client.post(f"/api/proposals/P-missing/{action}", json={}).status_code == 404


@pytest.mark.parametrize("action", ["reject", "defer"])
def test_decision_reason_length_is_validated_before_writing(tmp_path, action):
    memory = tmp_path / "memory"
    client = TestClient(create_app(memory))
    proposal = propose(client)
    response = client.post(
        f"/api/proposals/{proposal['proposal_id']}/{action}",
        json={"reason": "x" * 10001},
    )
    assert response.status_code == 422
    assert MemoryStore(memory).decisions() == []
    assert MemoryStore(memory).proposal(proposal["proposal_id"]).status.value == "discussing"
