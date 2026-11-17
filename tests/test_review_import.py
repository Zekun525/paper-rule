import json

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from paperrule.api.app import create_app
from paperrule.cli.main import app
from paperrule.domain.models import PaperProfile, ReviewFinding, ReviewReport, RuleRecord, RuleScope
from paperrule.persistence.store import MemoryStore
from paperrule.review.importing import import_report


@pytest.fixture
def memory(tmp_path, monkeypatch):
    root = tmp_path / "synthetic-memory"
    monkeypatch.setenv("PAPERRULE_MEMORY", str(root))
    store = MemoryStore(root)
    store.initialize()
    store.save_paper(PaperProfile(paper_id="synthetic-paper"))
    store.save_rule(RuleRecord(
        id="R-SYNTHETIC", short_title="Synthetic proof guidance",
        statement="Explain synthetic assumptions.", status="active",
        scope=RuleScope(paper_ids=["synthetic-paper"], sections=["proof"]),
    ))
    return store


def report():
    return ReviewReport(
        review_id="REV-SYNTHETIC", paper_id="synthetic-paper", section="proof",
        provider="external", model="synthetic-test",
        findings=[ReviewFinding(
            rule_id="R-SYNTHETIC", rule_version=1,
            description="Synthetic missing explanation.",
            quote="Synthetic claim.", evidence="Synthetic excerpt requires explanation.",
            review_type="semantic",
        )],
    )


def test_import_roundtrip_is_idempotent_and_does_not_change_active_rules(memory):
    before = memory.rules()
    original = report()
    assert import_report(memory, original) == original
    assert import_report(memory, original) == original
    assert memory.reviews() == [original]
    assert memory.rules() == before
    assert memory.decisions() == []


def test_existing_report_cannot_be_overwritten(memory):
    original = report()
    import_report(memory, original)
    with pytest.raises(ValueError, match="different content"):
        import_report(memory, original.model_copy(update={"task_summary": "Changed synthetic review"}))
    assert memory.reviews() == [original]


@pytest.mark.parametrize("change,expected", [
    ({"paper_id": "synthetic-missing"}, "Paper profile"),
    ({"paper_id": None}, "require a paper"),
    ({"section": "introduction"}, "outside scope"),
    ({"review_id": "../outside"}, "identifier"),
])
def test_invalid_report_is_not_saved(memory, change, expected):
    with pytest.raises(ValueError, match=expected):
        import_report(memory, report().model_copy(update=change))
    assert memory.reviews() == []


@pytest.mark.parametrize("change,expected", [
    ({"rule_id": "R-SYNTHETIC-UNKNOWN"}, "unknown rule"),
    ({"rule_version": 2}, "stale rule"),
])
def test_invalid_rule_reference_is_not_saved(memory, change, expected):
    value = report()
    value.findings = [value.findings[0].model_copy(update=change)]
    with pytest.raises(ValueError, match=expected):
        import_report(memory, value)
    assert memory.reviews() == []


def test_inactive_rule_reference_is_rejected(memory):
    rule = memory.rules()[0]
    rule.status = "deprecated"
    memory.save_rule(rule)
    with pytest.raises(ValueError, match="inactive rule"):
        import_report(memory, report())
    assert memory.reviews() == []


def test_cli_and_api_share_import_validation(memory, tmp_path):
    value = report()
    path = tmp_path / "synthetic-review.json"
    path.write_text(value.model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(app, ["review-import", str(path)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["review_id"] == value.review_id
    with TestClient(create_app(memory.root)) as client:
        response = client.post("/api/reviews/import", json=value.model_dump(mode="json"))
        assert response.status_code == 200
        assert client.get("/api/reviews").json() == [value.model_dump(mode="json")]
        invalid = value.model_copy(update={
            "review_id": "REV-SYNTHETIC-INVALID", "paper_id": "synthetic-missing",
        })
        assert client.post("/api/reviews/import", json=invalid.model_dump(mode="json")).status_code == 400
    path.write_text(invalid.model_dump_json(), encoding="utf-8")
    rejected = CliRunner().invoke(app, ["review-import", str(path)])
    assert rejected.exit_code != 0
    assert len(memory.reviews()) == 1
