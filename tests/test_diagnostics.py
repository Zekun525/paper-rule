from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.providers import OpenAIAPIProvider


def test_manual_diagnostics_do_not_claim_an_ai_connection(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "manual")
    client = TestClient(create_app(tmp_path / "synthetic-memory"))
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["provider"]["name"] == "manual"
    assert data["provider"]["configured"] is False
    assert data["provider"]["connection"] == "not_checked"
    assert data["counts"] == {
        "sources": 0, "feedback": 0, "rules": 0, "proposals": 0, "papers": 0,
    }
    assert client.get("/api/rules").json() == []


def test_config_detection_never_exposes_a_key_or_calls_the_model(tmp_path, monkeypatch):
    key = "sk" + "-" + "synthetic" * 5
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_API_KEY", key)

    def forbidden_chat(*args, **kwargs):
        raise AssertionError("Diagnostics must not send material to a model")

    monkeypatch.setattr(OpenAIAPIProvider, "chat", forbidden_chat)
    client = TestClient(create_app(tmp_path / "synthetic-memory"))
    response = client.get("/api/diagnostics")
    assert response.status_code == 200
    assert key not in response.text
    assert "OPENAI_API_KEY" not in response.text
    assert response.json()["provider"]["configured"] is True
    assert response.json()["provider"]["connection"] == "not_checked"


def test_unknown_provider_is_reported_without_pretending_it_is_available(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "synthetic-unknown-provider")
    response = TestClient(create_app(tmp_path / "synthetic-memory")).get("/api/diagnostics")
    assert response.status_code == 200
    assert response.json()["provider"]["configured"] is False
    assert response.json()["provider"]["connection"] == "not_checked"
