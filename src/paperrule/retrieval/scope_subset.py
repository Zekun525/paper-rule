"""Conservative scope containment proofs for explicitly approved rule relationships.

This proves containment of the existing structured filters. It does not interpret
natural-language exceptions or infer scope from hierarchy labels.
"""

from datetime import UTC, datetime

from paperrule.domain.models import RuleScope
from paperrule.retrieval.scope_filters import FIELDS, _parse

DIMENSIONS = {
    "paper": "paper_ids",
    "research_type": "research_types",
    "venue": "venues",
    "article_type": "article_types",
    "section": "sections",
    "task": "task_types",
}


def _constraints(
    scope: RuleScope,
) -> tuple[dict[str, set[str] | None], dict[str, set[str]]] | None:
    include, bare_include, unknown_include = _parse(scope.include)
    exclude, bare_exclude, unknown_exclude = _parse(scope.exclude)
    if unknown_include or unknown_exclude:
        return None
    allowed: dict[str, set[str] | None] = {
        field: set(values) if (values := getattr(scope, attribute)) else None
        for field, attribute in DIMENSIONS.items()
    }
    denied = {field: set(exclude.get(field, set())) for field in FIELDS}
    # Bare includes add a separate paper AND-condition, just as match_filters does.
    clauses = list(include.items())
    if bare_include:
        clauses.append(("paper", bare_include))
    for field, values in clauses:
        previous = allowed[field]
        allowed[field] = set(values) if previous is None else previous & values
    # A legacy bare exclusion rejects either that paper or that section.
    denied["paper"].update(bare_exclude)
    denied["section"].update(bare_exclude)
    for field, values in allowed.items():
        if values is not None:
            allowed[field] = values - denied[field]
    return allowed, denied


def _effective(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def prove_scope_subset(child: RuleScope, parent: RuleScope) -> tuple[bool, bool, str]:
    """Return (contained, strictly_narrower, reason), without changing either scope.

    Unknown selectors, contradictory finite filters and changed free-text
    exceptions cannot establish a usable override. False means unproven, rather
    than a claim that the scopes are necessarily disjoint.
    """
    if child.exceptions != parent.exceptions:
        return False, False, "scope_exceptions_require_clarification"
    child_constraints = _constraints(child)
    parent_constraints = _constraints(parent)
    if child_constraints is None or parent_constraints is None:
        return False, False, "scope_filters_require_clarification"
    child_allowed, child_denied = child_constraints
    parent_allowed, parent_denied = parent_constraints
    if any(values is not None and not values for values in child_allowed.values()):
        return False, False, "child_scope_has_no_matches"
    if any(values is not None and not values for values in parent_allowed.values()):
        return False, False, "parent_scope_has_no_matches"
    strict = False
    for field in DIMENSIONS:
        child_values, parent_values = child_allowed[field], parent_allowed[field]
        if parent_values is not None:
            if child_values is None or not child_values <= parent_values:
                return False, False, "scope_would_widen_" + field
            strict = strict or child_values != parent_values
        elif child_values is not None:
            if child_values & parent_denied[field]:
                return False, False, "scope_would_widen_" + field
            strict = True
        else:
            if not parent_denied[field] <= child_denied[field]:
                return False, False, "scope_would_widen_" + field
            strict = strict or child_denied[field] != parent_denied[field]
    try:
        child_time, parent_time = _effective(child.effective_from), _effective(parent.effective_from)
    except (OverflowError, ValueError):
        return False, False, "scope_effective_date_unresolved"
    if child_time < parent_time:
        return False, False, "effective_date_would_widen"
    strict = strict or child_time > parent_time
    return True, strict, "scope_subset" if strict else "scope_equal"
