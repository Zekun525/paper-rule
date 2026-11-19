from subprocess import TimeoutExpired

import pytest
from fastapi.testclient import TestClient as RawTestClient
from owner_client import TestClient
from test_sync_preview import RULE_PATH, amend, authority, devices

from paperrule.api.app import create_app
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.sync.git import GitSync, SyncError


def test_owner_can_fetch_and_preview_all_three_versions_without_approval(tmp_path, monkeypatch):
    first, local, second, other, base = devices(tmp_path)
    amend(second, other, "Explain the synthetic API remote assumption.")
    amend(first, local, "Explain the synthetic API local assumption.")
    before = authority(first, local)
    with TestClient(create_app(first.root)) as client:
        response = client.post("/api/sync/preview", json={})
        assert response.status_code == 200
        preview = response.json()
        assert preview["status"] == "diverged"
        assert preview["base_commit"] == base
        assert preview["local_commit"] == before[2]
        assert preview["remote_commit"] == other.git.head()
        assert preview["applies_changes"] is False
        assert preview["changes"][0]["local"]["rule"]["statement"] == (
            "Explain the synthetic API local assumption."
        )
        assert preview["changes"][0]["remote"]["rule"]["statement"] == (
            "Explain the synthetic API remote assumption."
        )
        fetch_calls = []
        original_run = GitSync.run

        def observe_reads(self, *args, **kwargs):
            if args and args[0] == "fetch":
                fetch_calls.append(args)
            return original_run(self, *args, **kwargs)

        monkeypatch.setattr(GitSync, "run", observe_reads)
        assert client.get("/api/sync/preview").status_code == 404
        assert fetch_calls == []
    assert authority(first, local) == before


def test_unauthorized_preview_does_not_fetch_or_change_authority(tmp_path):
    first, local, second, other, _ = devices(tmp_path)
    amend(second, other, "Explain the synthetic unauthorized remote assumption.")
    before = authority(first, local)
    tracking = local.git.run("rev-parse", "@{upstream}")
    app = create_app(first.root, owner_token="synthetic-owner-" + "0" * 48)
    with RawTestClient(app) as client:
        response = client.post("/api/sync/preview", json={})
        assert response.status_code in {401, 403}
    assert local.git.run("rev-parse", "@{upstream}") == tracking
    assert authority(first, local) == before


def test_unconfigured_remote_returns_guidance_without_creating_approval(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-unconfigured-memory")
    store.initialize()
    governance = Governance(store)
    governance.git.init()
    before = authority(store, governance)
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/sync/preview", json={})
        assert response.status_code == 400
        assert "尚未配置私有远端" in response.json()["detail"]
    assert authority(store, governance) == before


@pytest.mark.parametrize("failure", ["git", "timeout"])
def test_connection_errors_do_not_expose_private_output_or_change_rules(
    tmp_path, monkeypatch, failure,
):
    first, local, _, _, _ = devices(tmp_path)
    before = authority(first, local)
    original = GitSync.run

    def failing_fetch(self, *args, **kwargs):
        if args and args[0] == "fetch":
            if failure == "timeout":
                raise TimeoutExpired(["git", "fetch"], 1)
            raise SyncError("SENSITIVE-SYNTHETIC private connection output")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(GitSync, "run", failing_fetch)
    with TestClient(create_app(first.root)) as client:
        response = client.post("/api/sync/preview", json={})
        assert response.status_code == 503
        assert "已有规则仍保留在本机" in response.json()["detail"]
        assert "SENSITIVE-SYNTHETIC" not in response.text
    assert authority(first, local) == before


def test_invalid_remote_rule_is_not_imported_by_preview_endpoint(tmp_path):
    first, local, second, other, _ = devices(tmp_path)
    (second.root / RULE_PATH).write_text("{}", encoding="utf-8")
    other.git.run("add", "--", RULE_PATH)
    other.git.commit("Synthetic invalid API preview fixture")
    assert other.git.push()["status"] == "synced"
    before = authority(first, local)
    with TestClient(create_app(first.root)) as client:
        response = client.post("/api/sync/preview", json={})
        assert response.status_code == 503
    assert authority(first, local) == before
