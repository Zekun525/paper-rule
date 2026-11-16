from fastapi.testclient import TestClient

from paperrule.api.app import create_app
from paperrule.sync.git import GitSync


def approve_rule(client, rule):
    created = client.post("/api/proposals", json={"rule": rule})
    assert created.status_code == 200
    proposal = created.json()
    approved = client.post(
        f"/api/proposals/{proposal['proposal_id']}/approve",
        json={"proposal_hash": proposal["proposal_hash"]},
    )
    assert approved.status_code == 200


def test_paper_venue_change_recalculates_context_and_preserves_facts(tmp_path):
    memory = tmp_path / "synthetic-memory"
    client = TestClient(create_app(memory))
    profile = {
        "paper_id": "synthetic-paper",
        "title": "Synthetic theorem study",
        "research_type": "theory",
        "venue": "SYNTHETIC-A",
        "article_type": "full",
        "facts": ["Synthetic result requires independent samples."],
        "terms": ["synthetic-bound"],
    }
    assert client.post("/api/papers", json=profile).status_code == 200
    approve_rule(client, {
        "id": "R-GLOBAL", "short_title": "Explain assumptions",
        "statement": "State assumptions before the proof.",
    })
    approve_rule(client, {
        "id": "R-VENUE", "short_title": "Synthetic venue structure",
        "statement": "Provide the full discussion.",
        "scope": {
            "levels": ["publication"], "venues": ["SYNTHETIC-A"], "article_types": ["full"],
        },
    })
    response = client.post("/api/context", json={
        "paper_id": profile["paper_id"], "section": "proof", "task": "revise",
    })
    assert response.status_code == 200
    assert {item["rule"]["id"] for item in response.json()["rules"]} == {"R-GLOBAL", "R-VENUE"}
    assert response.json()["memory_commit"] == GitSync(memory).head()

    changed = client.get("/api/papers").json()[0]
    changed["venue"] = "SYNTHETIC-B"
    assert client.post("/api/papers", json=changed).status_code == 200
    reloaded = client.get("/api/papers").json()[0]
    assert reloaded["facts"] == profile["facts"]
    assert reloaded["terms"] == profile["terms"]
    revised_context = client.post("/api/context", json={"paper_id": profile["paper_id"]})
    assert revised_context.status_code == 200
    assert [item["rule"]["id"] for item in revised_context.json()["rules"]] == ["R-GLOBAL"]
    assert len(client.get("/api/rules").json()) == 2


def test_invalid_paper_identifier_is_rejected_without_writing_a_record(tmp_path):
    client = TestClient(create_app(tmp_path / "synthetic-memory"))
    response = client.post("/api/papers", json={"paper_id": "../outside"})
    assert response.status_code == 400
    assert client.get("/api/papers").json() == []
    assert not (tmp_path / "outside.json").exists()


def test_context_requires_a_saved_paper_profile(tmp_path):
    client = TestClient(create_app(tmp_path / "synthetic-memory"))
    response = client.post("/api/context", json={"paper_id": "missing-paper"})
    assert response.status_code == 404
