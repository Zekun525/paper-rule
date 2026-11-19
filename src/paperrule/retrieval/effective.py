"""Resolve explicitly approved overrides without modifying stored rule authority."""

from dataclasses import dataclass, field
from graphlib import CycleError, TopologicalSorter

from paperrule.domain.models import RuleRecord, RuleStatus
from paperrule.governance.relation_bindings import OVERRIDE_RELATIONS, target_digest
from paperrule.retrieval.relations import declared_conflicts
from paperrule.retrieval.scope_subset import prove_scope_subset


@dataclass
class EffectiveRules:
    rules: list[RuleRecord]
    excluded: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    issues: list[dict] = field(default_factory=list)


def resolve_overrides(rules: list[RuleRecord], applicable: list[RuleRecord]) -> EffectiveRules:
    """Apply version-bound overrides only within the caller's matched context.

    Unbound legacy relations, stale targets and unsupported containment proofs
    leave both rules available and produce explicit issues. Conflicting rules
    cannot be hidden by an override. Callers must carry issues into completeness
    and retain replacement rules when applying their context budgets.
    """
    known = {rule.id: rule for rule in rules}
    matched = {rule.id: rule for rule in applicable}
    issues = []
    if len(known) != len(rules) or len(matched) != len(applicable):
        return EffectiveRules(
            list(applicable), issues=[{
                "rule_id": "", "target_id": "", "reason": "ambiguous_rule_identifiers",
            }],
        )
    invalid = set()
    records = {}

    def issue(rule_id: str, target_id: str, reason: str) -> None:
        entry = {"rule_id": rule_id, "target_id": target_id, "reason": reason}
        if entry not in issues:
            issues.append(entry)
        invalid.add(rule_id)

    for source in applicable:
        for relation in source.relations:
            kind = relation.get("type", "")
            if relation.get("status", "candidate") != "approved" or kind not in OVERRIDE_RELATIONS:
                continue
            target_id = relation.get("target_id", "")
            target = known.get(target_id)
            if target is None:
                issue(source.id, target_id, "missing_override_target")
                continue
            if target_id == source.id:
                issue(source.id, target_id, "self_override")
                continue
            if source.status != RuleStatus.ACTIVE or target.status != RuleStatus.ACTIVE:
                issue(source.id, target_id, "inactive_override_rule")
                continue
            if not relation.get("target_version") or not relation.get("target_sha256"):
                issue(source.id, target_id, "override_target_binding_missing")
                continue
            if (relation["target_version"] != str(target.version)
                    or relation["target_sha256"] != target_digest(target)):
                issue(source.id, target_id, "override_target_binding_stale")
                continue
            contained, strict, reason = prove_scope_subset(source.scope, target.scope)
            if not contained or (kind != "supersedes" and not strict):
                issue(source.id, target_id, "override_" + reason)
                continue
            if target_id not in matched:
                issue(source.id, target_id, "override_target_outside_context")
                continue
            records[(source.id, target_id, kind)] = {
                "rule_id": source.id, "rule_version": source.version,
                "target_id": target_id, "target_version": target.version,
                "type": kind, "reason": "approved_" + kind,
            }

    conflicts, conflict_issues = declared_conflicts(rules, applicable)
    for conflict in conflicts:
        for rule_id in conflict["rule_ids"]:
            invalid.add(rule_id)
    for entry in conflict_issues:
        invalid.add(entry["rule_id"])
    # Keep existing conflict reporting separate, while preventing its participants
    # from silently disappearing through this resolver.
    graph = {key: set() for key in matched}
    for record in records.values():
        source_id, target_id = record["rule_id"], record["target_id"]
        if source_id not in invalid and target_id not in invalid:
            graph[source_id].add(target_id)

    while graph:
        try:
            tuple(TopologicalSorter(graph).static_order())
            break
        except CycleError as error:
            component = set(error.args[1])
            # Withhold the complete connected component so a dependency on a
            # cyclic override cannot conceal another unresolved participant.
            changed = True
            while changed:
                previous = set(component)
                for source_id, targets in graph.items():
                    if source_id in component or targets & component:
                        component.add(source_id)
                        component.update(targets)
                changed = component != previous
            for rule_id in sorted(component):
                issue(rule_id, "", "approved_override_cycle")
            graph = {
                key: targets - component for key, targets in graph.items()
                if key not in component
            }

    applied = [
        record for record in records.values()
        if record["rule_id"] in graph and record["target_id"] in graph[record["rule_id"]]
    ]
    suppressed = {record["target_id"] for record in applied}
    excluded = [{
        "rule_id": record["target_id"], "reason": record["reason"],
        "by_rule_id": record["rule_id"], "by_rule_version": record["rule_version"],
        "rule_version": record["target_version"],
    } for record in applied]
    return EffectiveRules(
        [rule for rule in applicable if rule.id not in suppressed],
        excluded=excluded, relations=applied, issues=issues,
    )
