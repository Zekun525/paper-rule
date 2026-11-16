import json

from typer.testing import CliRunner

from paperrule.cli.main import app
from paperrule.domain.models import RegressionCase, RuleRecord
from paperrule.persistence.store import MemoryStore
from paperrule.review.regression import reports, run_cases, run_stored_cases


def test_semantic_negative_case_is_unreviewed_instead_of_passing():
    rule = RuleRecord(id="G-synthetic", status="active", short_title="Synthetic",
                      statement="Explain the reasoning", check_method="semantic")
    case = RegressionCase(id="RT-synthetic", rule_id=rule.id,
                          input_text="Synthetic clear reasoning", expected="no_violation",
                          check_method="semantic")
    report = run_cases([case], [rule])
    assert report["passed"] == 0
    assert report["failed"] == 0
    assert report["unavailable"] == 1
    assert report["status"] == "incomplete"
    assert report["results"][0]["passed"] is None


def test_missing_rule_never_passes_a_negative_case():
    case = RegressionCase(id="RT-missing", rule_id="G-missing",
                          input_text="Synthetic text", expected="no_violation")
    report = run_cases([case], [])
    assert report["results"][0]["reason"] == "rule_not_found"
    assert report["passed"] == 0


def test_run_and_cli_report_are_persisted_with_evidence(tmp_path, monkeypatch):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    store.save_rule(RuleRecord(
        id="G-synthetic", status="active", short_title="Avoid vague claims",
        statement="avoid: very clearly", check_method="deterministic",
    ))
    store.save_regression(RegressionCase(
        id="RT-synthetic", rule_id="G-synthetic",
        input_text="The result is very clearly true.", expected="violation",
    ))
    first = run_stored_cases(store)
    assert first["passed"] == 1
    assert first["results"][0]["findings"][0]["quote"] == "very clearly"
    assert reports(store)[0]["run_id"] == first["run_id"]
    monkeypatch.setenv("PAPERRULE_MEMORY", str(store.root))
    runner = CliRunner()
    result = runner.invoke(app, ["regression", "run"])
    assert result.exit_code == 0, result.output
    second = json.loads(result.output)
    assert second["run_id"] != first["run_id"]
    result = runner.invoke(app, ["regression", "report", "--latest"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["run_id"] == second["run_id"]
