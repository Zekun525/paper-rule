"""Expose approved conflicts without selecting a winner or changing any rule."""

from paperrule.domain.models import RuleRecord


def declared_conflicts(
    rules: list[RuleRecord], applicable: list[RuleRecord],
) -> tuple[list[dict], list[dict]]:
    known = {rule.id: rule for rule in rules}
    matched = {rule.id: rule for rule in applicable}
    conflicts = {}
    issues = []
    for source in matched.values():
        for relation in source.relations:
            if (relation.get("status", "candidate") != "approved"
                    or relation.get("type") != "conflicts_with"):
                continue
            target_id = relation.get("target_id", "")
            if target_id not in known:
                issues.append({
                    "rule_id": source.id, "target_id": target_id,
                    "reason": "missing_conflict_target",
                })
                continue
            if target_id == source.id:
                issues.append({
                    "rule_id": source.id, "target_id": target_id,
                    "reason": "self_conflict",
                })
                continue
            if target_id not in matched:
                continue
            pair = tuple(sorted((source.id, target_id)))
            conflicts[pair] = {
                "rule_ids": list(pair),
                "rule_versions": {key: matched[key].version for key in pair},
                "reason": "approved_conflicting_rules",
            }
    return [conflicts[pair] for pair in sorted(conflicts)], issues
