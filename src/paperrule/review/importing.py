"""Validate external review data without treating it as rule approval."""

from paperrule.domain.models import ReviewReport, digest
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
        snapshots = {rule.id: rule for rule in report.rule_snapshot}
        if len(snapshots) != len(report.rule_snapshot):
            raise ValueError("Review snapshot contains duplicate rule identifiers")
        if report.rule_snapshot_sha256 is not None:
            expected = digest([rule.model_dump(mode="json") for rule in report.rule_snapshot])
            if report.rule_snapshot_sha256 != expected:
                raise ValueError("Review snapshot hash does not match its rule content")
        for rule in report.rule_snapshot:
            original = known.get(rule.id)
            if original is None or digest(original) != digest(rule):
                raise ValueError(f"Review snapshot does not match the current rule: {rule.id}")
        references = [(item.rule_id, item.version) for item in report.rules]
        references.extend((item.rule_id, item.rule_version) for item in report.coverage)
        for field in (report.rules, report.coverage):
            if len({item.rule_id for item in field}) != len(field):
                raise ValueError("Review contains duplicate rule or coverage identifiers")
        for rule_id, version in references:
            rule = known.get(rule_id)
            if rule is None:
                raise ValueError(f"Review references unknown rule {rule_id}")
            if rule.status.value != "active":
                raise ValueError(f"Review references inactive rule {rule_id}")
            if version != rule.version:
                raise ValueError(f"Review has stale rule version {rule_id}")
            if snapshots and rule_id not in snapshots:
                raise ValueError(f"Review references a rule absent from its snapshot: {rule_id}")
            if profile and not applies(rule, profile, report.section, report.task)[0]:
                raise ValueError(f"Review references a rule outside scope: {rule_id}")
            if profile is None and any((
                rule.scope.paper_ids, rule.scope.sections, rule.scope.task_types,
                rule.scope.research_types, rule.scope.venues, rule.scope.article_types,
                rule.scope.include, rule.scope.exclude, rule.scope.exceptions,
                rule.scope.effective_from,
            )):
                raise ValueError("Scoped review references require a paper profile")
        for item in report.coverage:
            if item.status != "checked" and item.checked_line_count:
                raise ValueError("Unreviewed coverage cannot claim checked lines")
        for finding in report.findings:
            rule = known.get(finding.rule_id)
            if rule is None:
                raise ValueError(f"Review finding references unknown rule {finding.rule_id}")
            if rule.status.value != "active":
                raise ValueError(f"Review finding references inactive rule {finding.rule_id}")
            if finding.rule_version != rule.version:
                raise ValueError(f"Review finding has stale rule version {finding.rule_id}")
            if snapshots and finding.rule_id not in snapshots:
                raise ValueError("Review finding references a rule absent from its snapshot")
            if profile and not applies(rule, profile, report.section, report.task)[0]:
                raise ValueError(f"Review finding references a rule outside scope: {finding.rule_id}")
            if profile is None and (
                rule.scope.paper_ids or rule.scope.sections or rule.scope.task_types
                or rule.scope.research_types or rule.scope.venues or rule.scope.article_types
            ):
                raise ValueError("Scoped review findings require a paper profile")
        store.save_review(report)
        return report
