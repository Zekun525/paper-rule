"""Pin effective relationships in drafts, before their exact approval hash is saved."""

from paperrule.domain.models import RuleRecord, RuleStatus, digest

OVERRIDE_RELATIONS = frozenset({"narrows", "exception_to", "supersedes"})
PIN_FIELDS = ("target_version", "target_sha256")


def _confirmed(relation: dict[str, str]) -> bool:
    return relation.get("status", "candidate") == "approved" and (
        relation.get("type") in OVERRIDE_RELATIONS
    )


def target_digest(rule: RuleRecord) -> str:
    """Bind the complete target state except the approval-generated audit identifier."""
    return digest(rule.model_dump(mode="json", exclude={"revision_id"}))


def _projected(
    planned: list[RuleRecord], known: dict[str, RuleRecord], operation: str,
) -> dict[str, RuleRecord]:
    result = {}
    for draft in planned:
        rule = draft.model_copy(deep=True)
        previous = known.get(rule.id)
        rule.version = previous.version + 1 if previous else 1
        rule.status = RuleStatus.DEPRECATED if operation == "deactivate" else (
            RuleStatus.ACTIVE if rule.status == RuleStatus.PROPOSED else rule.status
        )
        result[rule.id] = rule
    return result


def bind_draft_targets(
    planned: list[RuleRecord], known_rules: list[RuleRecord], operation: str,
) -> list[RuleRecord]:
    """Return copied drafts with reviewable pins for acyclic, available targets.

    Invalid or cyclic targets stay editable but unbound; approval rejects them.
    Candidate and conflict annotations retain their existing behavior.
    """
    drafts = [rule.model_copy(deep=True) for rule in planned]
    if operation == "one_off":
        return drafts
    if len({rule.id for rule in drafts}) != len(drafts):
        raise ValueError("Relationship binding requires unique planned rule identifiers")
    known = {rule.id: rule for rule in known_rules}
    if len(known) != len(known_rules):
        raise ValueError("Relationship binding requires unambiguous existing rules")
    for draft in drafts:
        for relation in draft.relations:
            if _confirmed(relation):
                for key in PIN_FIELDS:
                    relation.pop(key, None)
    projected = _projected(drafts, known, operation)
    waiting = set(projected)
    while waiting:
        ready = [
            key for key in sorted(waiting)
            if not any(
                _confirmed(relation) and relation.get("target_id") in waiting
                for relation in projected[key].relations
            )
        ]
        if not ready:
            break
        for key in ready:
            for relation in projected[key].relations:
                if not _confirmed(relation):
                    continue
                target_id = relation.get("target_id", "")
                target = projected.get(target_id) or known.get(target_id)
                if target is not None:
                    relation["target_version"] = str(target.version)
                    relation["target_sha256"] = target_digest(target)
            waiting.remove(key)
    for draft in drafts:
        if draft.id not in waiting:
            draft.relations = [dict(relation) for relation in projected[draft.id].relations]
    return drafts


def validate_target_bindings(
    planned: list[RuleRecord], known_rules: list[RuleRecord], operation: str,
) -> None:
    """Check approved content without filling or rewriting pins at approval time."""
    if operation == "one_off":
        return
    expected = bind_draft_targets(planned, known_rules, operation)
    known = {rule.id: rule for rule in known_rules}
    projected = _projected(expected, known, operation)
    for supplied, reviewed in zip(planned, expected, strict=True):
        for relation, expected_relation in zip(
            supplied.relations, reviewed.relations, strict=True,
        ):
            if not _confirmed(relation):
                continue
            if any(not expected_relation.get(key) for key in PIN_FIELDS):
                raise ValueError(
                    "Confirmed relationship requires an acyclic, reviewable target binding"
                )
            target_id = relation.get("target_id", "")
            target = projected.get(target_id) or known.get(target_id)
            if target is None:
                raise ValueError("Confirmed relationship requires an available target binding")
            if projected[supplied.id].status == RuleStatus.ACTIVE and target.status != RuleStatus.ACTIVE:
                raise ValueError("Confirmed relationship requires an active target")
            if any(relation.get(key) != expected_relation[key] for key in PIN_FIELDS):
                raise ValueError("Relationship target binding changed; review a revised proposal")
