import json
import platform

import pytest
from owner_client import TestClient
from typer.testing import CliRunner

from paperrule.api.app import create_app
from paperrule.cli.main import app as cli
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


@pytest.mark.parametrize("provider_name,configured", [
    ("manual", False), ("openai", True), ("openai_api", True),
    ("synthetic-unknown-provider", False), ("fake", False),
])
def test_doctor_matches_web_configuration_without_calling_a_model(
    tmp_path, monkeypatch, provider_name, configured,
):
    memory = tmp_path / "synthetic-doctor-memory"
    key = "synthetic-doctor-credential"
    monkeypatch.setenv("PAPERRULE_MEMORY", str(memory))
    monkeypatch.setenv("PAPERRULE_PROVIDER", provider_name)
    monkeypatch.setenv("OPENAI_API_KEY", key)

    def forbidden_chat(*args, **kwargs):
        raise AssertionError("Configuration checks must not send data to a model")

    monkeypatch.setattr(OpenAIAPIProvider, "chat", forbidden_chat)
    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["python"] == platform.python_version()
    assert data["memory"] == str(memory.resolve())
    assert data["provider"]["name"] == provider_name
    assert data["provider"]["configured"] is configured
    assert data["provider"]["connection"] == "not_checked"
    assert key not in result.output
    response = TestClient(create_app(memory)).get("/api/diagnostics")
    assert response.status_code == 200
    assert data["provider"] == response.json()["provider"]


def test_doctor_reports_missing_api_configuration_without_claiming_connection(
    tmp_path, monkeypatch,
):
    monkeypatch.setenv("PAPERRULE_MEMORY", str(tmp_path / "synthetic-unconfigured"))
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = CliRunner().invoke(cli, ["doctor"])
    assert result.exit_code == 0, result.output
    provider = json.loads(result.output)["provider"]
    assert provider["configured"] is False
    assert provider["connection"] == "not_checked"
