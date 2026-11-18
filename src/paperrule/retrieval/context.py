import json
from datetime import UTC, datetime

from paperrule.domain.models import PaperProfile, RuleRecord
from paperrule.retrieval.relations import declared_conflicts


def applies(rule: RuleRecord, paper: PaperProfile, section: str = "", task: str = "") -> tuple[bool, str]:
    scope = rule.scope
    if scope.effective_from is not None:
        effective = scope.effective_from
        if effective.tzinfo is None:
            effective = effective.replace(tzinfo=UTC)
        if effective > datetime.now(UTC):
            return False, "rule is not effective yet"
    if scope.paper_ids and paper.paper_id not in scope.paper_ids:
        return False, "different paper"
    if scope.research_types and paper.research_type not in scope.research_types:
        return False, "research type mismatch"
    if scope.venues and paper.venue not in scope.venues:
        return False, "publication mismatch"
    if scope.article_types and paper.article_type not in scope.article_types:
        return False, "article type mismatch"
    if scope.sections and section not in scope.sections:
        return False, "section not included"
    if scope.task_types and task not in scope.task_types:
        return False, "task not included"
    if paper.paper_id in scope.exclude or section in scope.exclude:
        return False, "explicitly excluded"
    return True, "scope matches paper, section, and task"


def build_context(
    rules: list[RuleRecord], paper: PaperProfile, section: str = "", task: str = "",
    *, max_rules: int = 40, max_rule_chars: int = 24000,
) -> dict:
    """Bound serialized rule entries; report mandatory omissions explicitly.

    Diagnostic exclusions expose identifiers and reasons, never unrelated rule text.
    The character budget covers the rules array, excluding transport metadata.
    """
    if not (max_rules > 0 and max_rule_chars > 1):
        raise ValueError("Context budgets must be positive")
    candidates = []
    excluded = []
    applicable = []
    for rule in rules:
        if rule.status.value != "active":
            excluded.append({"rule_id": rule.id, "reason": "rule is not active"})
            continue
        ok, reason = applies(rule, paper, section, task)
        if not ok:
            excluded.append({"rule_id": rule.id, "reason": reason})
            continue
        applicable.append(rule)
        scope = rule.scope
        mandatory = bool(
            rule.blocking or rule.severity in {"error", "critical", "must"}
            or scope.paper_ids or scope.sections or scope.task_types
        )
        specificity = sum(bool(value) for value in (
            scope.paper_ids, scope.sections, scope.task_types,
            scope.research_types, scope.venues, scope.article_types,
        ))
        entry = {"rule": rule.model_dump(mode="json"), "why_loaded": reason}
        candidates.append((mandatory, specificity, entry))
    unresolved_conflicts, relation_issues = declared_conflicts(rules, applicable)
    candidates.sort(key=lambda candidate: (-int(candidate[0]), -candidate[1]))
    selected = {}
    mandatory_omitted = []
    used = 2
    for mandatory, _, entry in candidates:
        rule_id = entry["rule"]["id"]
        if rule_id in selected:
            excluded.append({"rule_id": rule_id, "reason": "duplicate identifier"})
            continue
        size = len(json.dumps(entry, ensure_ascii=False, separators=(",", ":")))
        separator = int(bool(selected))
        if len(selected) >= max_rules or used + size + separator > max_rule_chars:
            excluded.append({"rule_id": rule_id, "reason": "context budget exceeded"})
            if mandatory:
                mandatory_omitted.append(rule_id)
            continue
        selected[rule_id] = entry
        used += size + separator
    # Preserve the caller's stable rule order after priority-based selection.
    matched = []
    for rule in rules:
        if rule.id in selected:
            matched.append(selected.pop(rule.id))
    return {
        "paper_id": paper.paper_id, "section": section, "task": task, "rules": matched,
        "excluded_rules": excluded,
        "complete": not mandatory_omitted and not unresolved_conflicts and not relation_issues,
        "unresolved_conflicts": unresolved_conflicts,
        "relation_issues": relation_issues,
        "mandatory_omitted": mandatory_omitted,
        "budget": {
            "max_rules": max_rules, "max_rule_chars": max_rule_chars,
            "used_rule_chars": used,
        },
    }
