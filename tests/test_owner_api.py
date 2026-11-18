from fastapi.testclient import TestClient as RawTestClient
from typer.testing import CliRunner

from paperrule.api.app import create_app
from paperrule.cli.main import app as cli
from paperrule.persistence.store import MemoryStore
from paperrule.sync.git import GitSync

TOKEN = "synthetic-integration-owner-" + "x" * 32


def test_actual_approval_requires_owner_session_and_csrf(tmp_path):
    root = tmp_path / "synthetic-memory"
    app = create_app(root, owner_token=TOKEN)
    client = RawTestClient(app, base_url="http://127.0.0.1",
                           client=("127.0.0.1", 50000))
    rule = {"id": "R-SYNTHETIC-OWNER", "short_title": "Synthetic owner rule",
            "statement": "Explain the synthetic assumption."}
    assert client.get("/healthz").json() == {"status": "ok"}
    assert client.get("/api/health").status_code == 401
    assert client.post("/api/proposals", json={"rule": rule}).status_code == 401
    assert MemoryStore(root).proposals() == []
    login = client.post("/api/session", json={"token": TOKEN})
    assert login.status_code == 200
    csrf = login.json()["csrf_token"]
    created = client.post("/api/proposals", json={"rule": rule},
                          headers={"X-CSRF-Token": csrf})
    assert created.status_code == 200
    proposal = created.json()
    before = GitSync(root).head()
    url = "/api/proposals/" + proposal["proposal_id"] + "/approve"
    body = {"proposal_hash": proposal["proposal_hash"]}
    assert client.post(url, json=body).status_code == 403
    assert client.post(url, json=body, headers={
        "X-CSRF-Token": csrf, "Origin": "https://synthetic-attacker.invalid",
    }).status_code == 403
    assert MemoryStore(root).rules() == []
    assert GitSync(root).head() == before
    approved = client.post(url, json=body, headers={"X-CSRF-Token": csrf})
    assert approved.status_code == 200
    assert MemoryStore(root).rule(rule["id"]).status.value == "active"
    after = GitSync(root).head()
    assert after != before
    assert client.post(url, json=body, headers={"X-CSRF-Token": csrf}).status_code == 200
    assert GitSync(root).head() == after


def test_service_restart_does_not_accept_previous_browser_session(tmp_path):
    root = tmp_path / "synthetic-memory"
    first = RawTestClient(create_app(root, owner_token=TOKEN),
                          base_url="http://127.0.0.1", client=("127.0.0.1", 50000))
    assert first.post("/api/session", json={"token": TOKEN}).status_code == 200
    second = RawTestClient(create_app(root), base_url="http://127.0.0.1",
                           client=("127.0.0.1", 50000), cookies=first.cookies)
    assert second.get("/api/rules").status_code == 401
    assert second.post("/api/session", json={"token": TOKEN}).status_code == 401


def test_cli_prints_owner_link_and_keeps_loopback_binding(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_MEMORY", str(tmp_path / "synthetic-memory"))
    captured = {}

    def run(application, **kwargs):
        captured["application"] = application
        captured.update(kwargs)

    monkeypatch.setattr("paperrule.cli.main.uvicorn.run", run)
    result = CliRunner().invoke(cli, ["app"])
    assert result.exit_code == 0, result.output
    token = captured["application"].state.owner_auth.owner_token
    assert "http://127.0.0.1:8765/#owner_token=" + token in result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["proxy_headers"] is False
