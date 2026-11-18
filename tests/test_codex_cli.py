import json
from pathlib import Path

from owner_client import TestClient
from typer.testing import CliRunner

from paperrule.api.app import create_app
from paperrule.cli.main import app
from paperrule.domain.models import PaperProfile
from paperrule.persistence.store import MemoryStore
from paperrule.sync.git import GitSync

runner = CliRunner()


def test_user_scope_cli_writes_only_to_simulated_home_and_project(tmp_path, monkeypatch):
    home = tmp_path / "synthetic-home"
    home.mkdir()
    project = tmp_path / "synthetic-paper"
    project.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    result = runner.invoke(app, [
        "install-codex", "--paper", str(project), "--scope", "user",
    ])
    assert result.exit_code == 0, result.output
    skill = home / ".agents" / "skills" / "paperrule" / "SKILL.md"
    assert skill.exists()
    assert not (project / ".agents").exists()
    result = runner.invoke(app, [
        "uninstall-codex", "--paper", str(project), "--scope", "user",
    ])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["skill_removed"] is True
    assert not skill.exists()


def test_documented_install_and_uninstall_commands_preserve_project(tmp_path):
    project = tmp_path / "synthetic paper project"
    project.mkdir()
    agents = project / "AGENTS.md"
    original = b"Preserve synthetic project instructions."
    agents.write_bytes(original)
    result = runner.invoke(app, ["install-codex", "--paper", str(project), "--scope", "repo"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["skill_created"] is True
    skill = project / ".agents" / "skills" / "paperrule" / "SKILL.md"
    assert skill.is_file()
    result = runner.invoke(app, ["uninstall-codex", "--paper", str(project)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["instructions_removed"] is True
    assert agents.read_bytes() == original
    assert not skill.exists()


def test_cli_install_reports_custom_skill_without_overwriting_it(tmp_path):
    skill = tmp_path / ".agents" / "skills" / "paperrule" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    original = b"Synthetic user managed skill"
    skill.write_bytes(original)
    result = runner.invoke(app, ["install-codex", "--paper", str(tmp_path)])
    assert result.exit_code != 0
    assert "user-managed" in result.output
    assert skill.read_bytes() == original
    assert not (tmp_path / "AGENTS.md").exists()


def test_documented_context_command_returns_same_snapshot_as_api(tmp_path, monkeypatch):
    memory = tmp_path / "synthetic-memory"
    monkeypatch.setenv("PAPERRULE_MEMORY", str(memory))
    store = MemoryStore(memory)
    store.initialize()
    GitSync(memory).init()
    store.save_paper(PaperProfile(paper_id="synthetic-paper"))
    result = runner.invoke(app, [
        "context", "--paper", "synthetic-paper",
        "--section", "introduction", "--task", "revise", "--format", "json",
    ])
    assert result.exit_code == 0, result.output
    bundle = json.loads(result.output)
    assert bundle["memory_commit"] == GitSync(memory).head()
    with TestClient(create_app(memory)) as client:
        response = client.post("/api/context", json={
            "paper_id": "synthetic-paper", "section": "introduction", "task": "revise",
        })
    assert response.status_code == 200
    assert bundle == response.json()


def test_cli_context_rejects_unsupported_format_before_creating_memory(tmp_path, monkeypatch):
    memory = tmp_path / "must-not-be-created"
    monkeypatch.setenv("PAPERRULE_MEMORY", str(memory))
    result = runner.invoke(app, ["context", "--paper", "synthetic", "--format", "yaml"])
    assert result.exit_code != 0
    assert "Only json output is supported" in result.output
    assert not memory.exists()
