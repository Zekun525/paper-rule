"""Validate external review data without treating it as rule approval."""

from paperrule.domain.models import ReviewReport
from paperrule.persistence.store import MemoryStore, identifier
from paperrule.retrieval.context import applies


def import_report(store: MemoryStore, report: ReviewReport) -> ReviewReport:
    identifier(report.review_id)
    with store.locked():
        existing = next((r for r in store.reviews() if r.review_id == report.review_id), None)
        if existing is not None:
            if existing != report:
                raise ValueError("Review identifier already exists with different content")
            return existing
        profile = None
        if report.paper_id:
            profile = next((p for p in store.papers() if p.paper_id == report.paper_id), None)
            if profile is None:
                raise ValueError("Paper profile was not found")
        known = {r.id: r for r in store.rules()}
        for finding in report.findings:
            rule = known.get(finding.rule_id)
            if rule is None:
                raise ValueError(f"Review finding references unknown rule {finding.rule_id}")
            if rule.status.value != "active":
                raise ValueError(f"Review finding references inactive rule {finding.rule_id}")
            if finding.rule_version != rule.version:
                raise ValueError(f"Review finding has stale rule version {finding.rule_id}")
            if profile and not applies(rule, profile, report.section, report.task)[0]:
                raise ValueError(f"Review finding references a rule outside scope: {finding.rule_id}")
            if profile is None and (
                rule.scope.paper_ids or rule.scope.sections or rule.scope.task_types
                or rule.scope.research_types or rule.scope.venues or rule.scope.article_types
            ):
                raise ValueError("Scoped review findings require a paper profile")
        store.save_review(report)
        return report
