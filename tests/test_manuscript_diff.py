import json
import subprocess

import pytest
from typer.testing import CliRunner

from paperrule.cli.main import app
from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.persistence.store import MemoryStore
from paperrule.review.files import changed_documents


def git(root, *arguments):
    return subprocess.run(
        ["git", "-c", "core.hooksPath=", "-c", "core.fsmonitor=false", *arguments],
        cwd=root, capture_output=True, check=True,
    ).stdout


@pytest.fixture
def manuscript(tmp_path, monkeypatch):
    root = tmp_path / "synthetic paper"
    root.mkdir()
    git(root, "init", "-b", "main")
    main = root / "main.tex"
    main.write_text(
        "Synthetic title." + chr(10)
        + "This is obviously unchanged." + chr(10)
        + "A synthetic clean claim." + chr(10),
        encoding="utf-8",
    )
    git(root, "add", "--", "main.tex")
    git(root, "-c", "user.name=Synthetic test", "-c", "user.email=synthetic@localhost",
        "commit", "--no-gpg-sign", "-m", "Synthetic manuscript baseline")
    memory = MemoryStore(tmp_path / "synthetic-memory")
    memory.initialize()
    monkeypatch.setenv("PAPERRULE_MEMORY", str(memory.root))
    memory.save_paper(PaperProfile(paper_id="synthetic-paper", project_path=str(root)))
    memory.save_rule(RuleRecord(
        id="R-SYNTHETIC", status="active", short_title="Synthetic phrase check",
        statement="avoid: obviously", check_method="deterministic",
    ))
    return root, memory


def run_check(*arguments):
    result = CliRunner().invoke(app, ["check", *arguments])
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_diff_checks_new_lines_and_preserves_baseline_and_worktree(manuscript):
    root, memory = manuscript
    main = root / "main.tex"
    changed = main.read_text(encoding="utf-8").replace(
        "A synthetic clean claim.", "A synthetic obviously changed claim.",
    )
    main.write_text(changed, encoding="utf-8")
    before_commit = git(root, "rev-parse", "HEAD").strip().decode("ascii")
    before_status = git(root, "status", "--porcelain")
    before_rules = memory.rules()
    result = run_check("--paper", "synthetic-paper", "--diff")
    assert result["paper_commit"] == before_commit
    assert result["diff_mode"] is True
    assert result["status"] == "findings"
    assert [finding["location"] for finding in result["findings"]] == ["main.tex:3"]
    assert result["findings"][0]["rule_id"] == "R-SYNTHETIC"
    assert result["findings"][0]["quote"] == "A synthetic obviously changed claim."
    assert "diff" in result["files"][0]
    assert result["semantic_status"] == "not_reviewed"
    assert result["latex_build_status"] == "not_run"
    assert main.read_text(encoding="utf-8") == changed
    assert git(root, "status", "--porcelain") == before_status
    assert git(root, "rev-parse", "HEAD").strip().decode("ascii") == before_commit
    assert memory.rules() == before_rules
    assert memory.decisions() == []


def test_staged_and_untracked_unicode_file_names_are_checked(manuscript):
    root, _ = manuscript
    staged = root / "synthetic staged.tex"
    staged.write_text("Synthetic obviously staged text.", encoding="utf-8")
    git(root, "add", "--", staged.name)
    untracked = root / "合成 未跟踪.tex"
    untracked.write_text("Synthetic obviously untracked text.", encoding="utf-8")
    (root / "synthetic-image.png").write_bytes(b"Synthetic image placeholder")
    result = run_check("--paper", "synthetic-paper", "--diff")
    assert {item["location"] for item in result["findings"]} == {
        staged.name + ":1", untracked.name + ":1",
    }
    assert len(result["files"]) == 2


def test_deletion_does_not_report_removed_violation_as_current_text(manuscript):
    root, _ = manuscript
    main = root / "main.tex"
    main.write_text("Synthetic title." + chr(10), encoding="utf-8")
    result = run_check("--paper", "synthetic-paper", "--diff")
    assert result["findings"] == []
    assert len(result["files"]) == 1
    assert "-This is obviously unchanged." in result["files"][0]["diff"]


def test_full_text_checks_all_occurrences_and_filters_other_paper(manuscript):
    root, memory = manuscript
    memory.save_rule(RuleRecord(
        id="R-SYNTHETIC-OTHER", status="active", short_title="Other synthetic paper",
        statement="avoid: title", check_method="deterministic",
        scope=RuleScope(paper_ids=["synthetic-other"]),
    ))
    result = run_check(str(root / "main.tex"), "--paper", "synthetic-paper")
    assert result["diff_mode"] is False
    assert [finding["rule_id"] for finding in result["findings"]] == ["R-SYNTHETIC"]
    assert result["findings"][0]["location"].endswith("main.tex:2")


def test_semantic_rules_are_explicitly_unreviewed(manuscript):
    root, memory = manuscript
    memory.save_rule(RuleRecord(
        id="R-SYNTHETIC-SEMANTIC", status="active",
        short_title="Synthetic semantic requirement", statement="Explain the proof.",
        check_method="semantic",
    ))
    result = run_check(str(root / "main.tex"), "--paper", "synthetic-paper")
    assert result["status"] == "incomplete"
    assert result["unavailable"] == [{
        "rule_id": "R-SYNTHETIC-SEMANTIC", "rule_version": 1,
        "reason": "semantic_not_reviewed",
    }]
    assert result["findings"][0]["rule_id"] == "R-SYNTHETIC"


def test_diff_does_not_run_configured_external_diff_command(manuscript):
    root, _ = manuscript
    git(root, "config", "--local", "diff.external", "synthetic-command-that-must-not-run")
    main = root / "main.tex"
    main.write_text("Synthetic obviously revised manuscript.", encoding="utf-8")
    documents, _ = changed_documents(root)
    assert len(documents) == 1
    assert documents[0]["changed_lines"] == {1}


def test_nested_project_is_rejected_instead_of_reviewing_parent_repository(manuscript):
    root, memory = manuscript
    nested = root / "synthetic-nested"
    nested.mkdir()
    memory.save_paper(PaperProfile(paper_id="synthetic-paper", project_path=str(nested)))
    result = CliRunner().invoke(app, ["check", "--paper", "synthetic-paper", "--diff"])
    assert result.exit_code != 0
    assert "root of its own Git repository" in result.output


def test_clean_diff_is_not_reported_as_paper_review_complete(manuscript):
    result = run_check("--paper", "synthetic-paper", "--diff")
    assert result["files"] == []
    assert result["status"] == "not_reviewed"


def test_missing_paper_is_a_readable_cli_error(manuscript):
    result = CliRunner().invoke(app, ["check", "--paper", "synthetic-missing", "--diff"])
    assert result.exit_code != 0
    assert "was not found" in result.output
