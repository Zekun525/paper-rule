import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import RuleRecord
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore


@pytest.fixture
def history(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    gov = Governance(store)
    first = gov.propose(RuleRecord(
        id="R-SYNTHETIC-A", short_title="Synthetic initial guidance",
        statement="Explain synthetic assumptions.",
    ))
    gov.approve(first.proposal_id, first.proposal_hash)
    target = gov.git.head()
    second = gov.propose(RuleRecord(
        id="R-SYNTHETIC-B", short_title="Synthetic later guidance",
        statement="Preserve synthetic notation.",
    ))
    gov.approve(second.proposal_id, second.proposal_hash)
    return store, gov, target


def test_restore_lists_actual_commits_and_preview_does_not_change_authority(history):
    store, gov, target = history
    rules = store.rules()
    head = gov.git.head()
    decisions = store.decisions()
    with TestClient(create_app(store.root)) as client:
        response = client.get("/api/restore")
        assert response.status_code == 200
        assert response.json()["available"] is True
        assert target in {item["commit"] for item in response.json()["snapshots"]}
        preview = client.post("/api/restore/preview", json={"commit": target})
        assert preview.status_code == 200
        value = preview.json()
        assert value["target_commit"] == target
        assert value["baseline_commit"] == head
        assert value["requires_approval"] is True
        assert [change["rule_id"] for change in value["changes"]] == ["R-SYNTHETIC-B"]
        assert value["changes"][0]["action"] == "deactivate"
    assert store.rules() == rules
    assert store.decisions() == decisions
    assert gov.git.head() == head


def test_restore_only_changes_planned_rules_after_exact_hash_approval(history):
    store, gov, target = history
    original_a = store.rule("R-SYNTHETIC-A")
    head = gov.git.head()
    preview = gov.preview_restore(target)
    proposal = gov.restore(target, preview["baseline_commit"])
    assert store.rule("R-SYNTHETIC-B").status.value == "active"
    assert gov.git.head() == head
    assert proposal.operation == "restore"
    assert proposal.after.id == "R-SYNTHETIC-B"
    gov.approve(proposal.proposal_id, proposal.proposal_hash)
    assert store.rule("R-SYNTHETIC-A") == original_a
    assert store.rule("R-SYNTHETIC-B").status.value == "deprecated"
    assert store.rule("R-SYNTHETIC-B").version == 2
    assert gov.git.head() != head
    assert gov.git.run("rev-parse", "HEAD^") == head
    assert gov.approve(proposal.proposal_id, proposal.proposal_hash)[1] == "already-applied"


def test_stale_preview_is_a_409_and_does_not_create_restore_proposal(history):
    store, gov, target = history
    baseline = gov.git.head()
    later = gov.propose(RuleRecord(
        id="R-SYNTHETIC-C", short_title="Synthetic intervening change",
        statement="Explain synthetic scope.",
    ))
    gov.approve(later.proposal_id, later.proposal_hash)
    before = store.proposals()
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/restore", json={
            "commit": target, "baseline_commit": baseline,
        })
        assert response.status_code == 409
    assert store.proposals() == before
    assert store.rule("R-SYNTHETIC-C").status.value == "active"


def test_unknown_commit_is_rejected_without_modifying_rules(history):
    store, _gov, _ = history
    before = store.rules()
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/restore/preview", json={"commit": "0" * 40})
        assert response.status_code == 400
    assert store.rules() == before


def test_initial_memory_reports_no_snapshots(tmp_path):
    with TestClient(create_app(tmp_path / "synthetic-memory")) as client:
        result = client.get("/api/restore")
        assert result.status_code == 200
        assert result.json()["available"] is False
        assert result.json()["snapshots"] == []
