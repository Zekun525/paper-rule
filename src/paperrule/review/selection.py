"""Select review rules with the same approved overrides used by context retrieval."""

from dataclasses import dataclass

from paperrule.domain.models import PaperProfile, RuleRecord
from paperrule.retrieval.context import applies
from paperrule.retrieval.effective import resolve_overrides
from paperrule.retrieval.relations import declared_conflicts
from paperrule.retrieval.scope_filters import UNRESOLVED_SCOPE


@dataclass
class ReviewSelection:
    rules: list[RuleRecord]
    unavailable: list[dict]
    blocked: dict[str, str]
    notes: list[str]
    unresolved: list[str]


def select_review_rules(
    rules: list[RuleRecord], profile: PaperProfile | None, section: str, task: str,
) -> ReviewSelection:
    applicable = []
    unavailable = []
    for rule in rules:
        if rule.status.value != "active":
            continue
        if profile is not None:
            included, reason = applies(rule, profile, section, task)
            if included:
                applicable.append(rule)
            elif reason == UNRESOLVED_SCOPE:
                unavailable.append({
                    "rule_id": rule.id, "rule_version": rule.version,
                    "reason": "scope_condition_unresolved",
                })
        elif not any((
            rule.scope.paper_ids, rule.scope.sections, rule.scope.task_types,
            rule.scope.research_types, rule.scope.venues, rule.scope.article_types,
            rule.scope.include, rule.scope.exclude, rule.scope.exceptions,
            rule.scope.effective_from,
        )):
            applicable.append(rule)
    resolution = resolve_overrides(rules, applicable)
    conflicts, legacy_issues = declared_conflicts(rules, applicable)
    selected_ids = {rule.id for rule in resolution.rules}
    blocked = {
        rule_id: "rule_conflict_unresolved"
        for conflict in conflicts for rule_id in conflict["rule_ids"]
        if rule_id in selected_ids
    }
    unresolved = [
        "、".join(conflict["rule_ids"]) + "：存在尚未解决的规则冲突。"
        for conflict in conflicts
    ]
    for issue in [*legacy_issues, *resolution.issues]:
        for rule_id in (issue["rule_id"], issue.get("target_id", "")):
            if rule_id in selected_ids:
                blocked.setdefault(rule_id, "rule_relation_unresolved")
        unresolved.append(
            issue["rule_id"] + "：规则关系需要重新核对（" + issue["reason"] +
            "；目标 " + (issue.get("target_id") or "未指定") + "）。"
        )
    relation_labels = {
        "approved_narrows": "已批准的范围限定",
        "approved_exception_to": "已批准的局部例外",
        "approved_supersedes": "已批准的替代规则",
    }
    notes = [
        row["rule_id"] + " · v" + str(row["rule_version"]) +
        "：依据" + relation_labels.get(row["reason"], "已批准的规则关系") +
        "，本次不检查此规则；采用规则 " +
        row["by_rule_id"] + " · v" + str(row["by_rule_version"]) +
        "。原规则记录未被修改。"
        for row in resolution.excluded
    ]
    return ReviewSelection(resolution.rules, unavailable, blocked, notes, unresolved)
