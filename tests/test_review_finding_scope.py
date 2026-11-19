from datetime import UTC, datetime

import pytest

from paperrule.domain.models import ReviewReport, RuleRecord, RuleScope
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.review.check import check_text
from paperrule.review.importing import import_report


def review_fixture(tmp_path, constraints):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    gov = Governance(store)
    proposal = gov.propose(RuleRecord(
        id="G-SYNTHETIC-SCOPE", short_title="Synthetic scoped phrase",
        statement="avoid: Synthetic restricted phrase", check_method="deterministic",
        scope=RuleScope(**constraints),
    ))
    gov.approve(proposal.proposal_id, proposal.proposal_hash, actor="synthetic-test")
    rule = store.rule(proposal.after.id)
    report = ReviewReport(
        review_id="REV-SYNTHETIC-SCOPE",
        findings=check_text("Synthetic restricted phrase", [rule]),
    )
    assert len(report.findings) == 1
    assert report.rules == [] and report.coverage == []
    return store, gov, rule, report


@pytest.mark.parametrize("constraints", [
    {"include": ["section:Proof"]},
    {"exclude": ["section:Experiments"]},
    {"exceptions": ["Routine algebra may be omitted."]},
    {"effective_from": datetime(2020, 1, 1, tzinfo=UTC)},
], ids=["include", "exclude", "exceptions", "effective-date"])
def test_finding_only_scoped_reports_require_paper_profile(tmp_path, constraints):
    store, gov, rule, report = review_fixture(tmp_path, constraints)
    original_rule = rule.model_dump_json()
    original_head = gov.git.head()
    with pytest.raises(ValueError, match="paper profile"):
        import_report(store, report)
    assert store.reviews() == []
    assert store.rule(rule.id).model_dump_json() == original_rule
    assert gov.git.head() == original_head


def test_finding_only_unscoped_report_remains_valid(tmp_path):
    store, gov, rule, report = review_fixture(tmp_path, {})
    original_rule = rule.model_dump_json()
    original_head = gov.git.head()
    assert import_report(store, report) == report
    assert store.reviews() == [report]
    assert store.rule(rule.id).model_dump_json() == original_rule
    assert gov.git.head() == original_head
