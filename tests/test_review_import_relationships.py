import pytest
from test_review_relationship_selection import manuscript, prepare

from paperrule.domain.models import ReviewCoverage, ReviewReport, ReviewRuleVersion
from paperrule.review.check import check_text
from paperrule.review.files import check_documents
from paperrule.review.importing import import_report


@pytest.mark.parametrize("claim", ["reference", "coverage", "finding"])
def test_import_rejects_replaced_rule_claims_without_persistence(tmp_path, claim):
    store, governance, profile, _ = prepare(tmp_path)
    rule = store.rule("R-SYNTHETIC-PARENT")
    report = ReviewReport(review_id="REV-SYNTHETIC-REPLACED", paper_id=profile.paper_id)
    if claim == "reference":
        report.rules = [ReviewRuleVersion(rule_id=rule.id, version=rule.version)]
    elif claim == "coverage":
        report.coverage = [ReviewCoverage(
            rule_id=rule.id, rule_version=rule.version, status="checked", checked_line_count=1,
        )]
    else:
        report.findings = check_text(manuscript()["text"], [rule])
        assert report.findings
    baseline = store.reviews(), store.rules(), store.decisions(), governance.git.head()
    with pytest.raises(ValueError, match="replaced"):
        import_report(store, report)
    assert (store.reviews(), store.rules(), store.decisions(), governance.git.head()) == baseline


@pytest.mark.parametrize("conflict", [False, True])
def test_unavailable_relationship_reports_round_trip_but_completed_claims_are_rejected(
    tmp_path, conflict,
):
    store, governance, profile, _ = prepare(tmp_path, conflict=conflict)
    if not conflict:
        parent = store.rule("R-SYNTHETIC-PARENT").model_copy(deep=True)
        parent.statement = "avoid: synthetic revised phrase"
        proposal = governance.propose(parent, "amend")
        governance.approve(proposal.proposal_id, proposal.proposal_hash)
    payload = check_documents(store, [manuscript()], profile)
    payload["review_id"] = "REV-SYNTHETIC-UNAVAILABLE-IMPORT"
    report = ReviewReport.model_validate(payload)
    assert report.coverage and all(row.status == "unavailable" for row in report.coverage)
    baseline = store.rules(), store.decisions(), governance.git.head()
    assert import_report(store, report) == report
    assert import_report(store, report) == report
    forged = report.model_copy(deep=True)
    forged.review_id = "REV-SYNTHETIC-FORGED-CHECKED"
    forged.coverage[0].status = "checked"
    forged.coverage[0].checked_line_count = 1
    saved = store.reviews()
    with pytest.raises(ValueError, match="Unresolved"):
        import_report(store, forged)
    forged = report.model_copy(deep=True)
    forged.review_id = "REV-SYNTHETIC-FORGED-FINDING"
    forged.findings = check_text(manuscript()["text"], store.rules())
    assert forged.findings
    with pytest.raises(ValueError, match="Unresolved"):
        import_report(store, forged)
    assert store.reviews() == saved
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


def test_other_paper_can_import_parent_findings(tmp_path):
    store, _, _, other = prepare(tmp_path)
    rule = store.rule("R-SYNTHETIC-PARENT")
    report = ReviewReport(
        review_id="REV-SYNTHETIC-OTHER-PAPER", paper_id=other.paper_id,
        findings=check_text(manuscript()["text"], [rule]),
    )
    assert report.findings
    assert import_report(store, report) == report
