import json

import pytest

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.governance.relation_bindings import target_digest
from paperrule.retrieval.context import applies
from paperrule.retrieval.effective import resolve_overrides


def guidance(rule_id, paper_ids=None):
    return RuleRecord(
        id=rule_id, status="active", short_title="Synthetic relationship guidance",
        statement="State the synthetic assumptions.",
        scope=RuleScope(paper_ids=paper_ids or []),
    )


def relate(source, target, kind="exception_to", state="approved"):
    source.relations.append({
        "type": kind, "status": state, "target_id": target.id,
        "target_version": str(target.version), "target_sha256": target_digest(target),
    })


def applicable(rules, paper_id="synthetic-a"):
    profile = PaperProfile(paper_id=paper_id)
    return [rule for rule in rules
            if rule.status.value == "active" and applies(rule, profile)[0]]


@pytest.mark.parametrize("kind", ["narrows", "exception_to", "supersedes"])
def test_explicit_override_is_local_and_preserves_all_authority(kind):
    parent = guidance("R-SYNTHETIC-GENERAL")
    child = guidance("R-SYNTHETIC-LOCAL", ["synthetic-a"])
    relate(child, parent, kind)
    rules = [parent, child]
    original = [rule.model_dump_json() for rule in rules]
    local = resolve_overrides(rules, applicable(rules))
    assert [rule.id for rule in local.rules] == [child.id]
    assert local.issues == []
    assert local.excluded == [{
        "rule_id": parent.id, "reason": "approved_" + kind,
        "by_rule_id": child.id, "by_rule_version": 1, "rule_version": 1,
    }]
    other = resolve_overrides(rules, applicable(rules, "synthetic-b"))
    assert [rule.id for rule in other.rules] == [parent.id]
    assert other.excluded == []
    assert other.relations == []
    assert other.issues == []
    assert child.statement not in json.dumps(other.excluded)
    assert [rule.model_dump_json() for rule in rules] == original


def test_candidate_cannot_suppress_a_matching_rule():
    parent = guidance("R-SYNTHETIC-GENERAL")
    child = guidance("R-SYNTHETIC-LOCAL", ["synthetic-a"])
    relate(child, parent, state="candidate")
    result = resolve_overrides([parent, child], [parent, child])
    assert result.rules == [parent, child]
    assert result.excluded == result.relations == result.issues == []


@pytest.mark.parametrize("change,reason", [
    ("missing-pin", "override_target_binding_missing"),
    ("changed-target", "override_target_binding_stale"),
    ("changed-target-version", "override_target_binding_stale"),
    ("wider-child", "override_scope_would_widen_paper"),
    ("equal-child", "override_scope_equal"),
    ("missing-target", "missing_override_target"),
])
def test_broken_override_preserves_both_rules_and_explains_the_issue(change, reason):
    parent = guidance("R-SYNTHETIC-GENERAL")
    child = guidance("R-SYNTHETIC-LOCAL", ["synthetic-a"])
    if change == "wider-child":
        parent.scope.paper_ids = ["synthetic-a"]
        child.scope.paper_ids = []
    relate(child, parent)
    if change == "missing-pin":
        child.relations[0].pop("target_sha256")
    elif change == "changed-target":
        parent.statement = "Explain the revised synthetic assumptions."
    elif change == "changed-target-version":
        parent.version += 1
    elif change == "equal-child":
        child.scope.paper_ids = []
    rules = [child] if change == "missing-target" else [parent, child]
    result = resolve_overrides(rules, rules)
    assert result.rules == rules
    assert result.excluded == []
    assert result.relations == []
    assert result.issues == [{
        "rule_id": child.id, "target_id": parent.id, "reason": reason,
    }]


def test_approved_chain_retains_the_most_local_rule_and_explains_each_edge():
    general = guidance("R-SYNTHETIC-GENERAL")
    intermediate = guidance("R-SYNTHETIC-MIDDLE", ["synthetic-a", "synthetic-b"])
    local = guidance("R-SYNTHETIC-LOCAL", ["synthetic-a"])
    relate(intermediate, general)
    relate(local, intermediate)
    rules = [general, intermediate, local]
    result = resolve_overrides(rules, applicable(rules))
    assert result.rules == [local]
    assert {row["rule_id"] for row in result.excluded} == {general.id, intermediate.id}
    assert len(result.relations) == 2
    assert result.issues == []
    elsewhere = resolve_overrides(rules, applicable(rules, "synthetic-b"))
    assert elsewhere.rules == [intermediate]
    assert len(elsewhere.excluded) == 1


def test_approved_conflict_cannot_be_hidden_by_an_override():
    parent = guidance("R-SYNTHETIC-GENERAL")
    child = guidance("R-SYNTHETIC-LOCAL", ["synthetic-a"])
    relate(child, parent)
    child.relations.append({
        "type": "conflicts_with", "target_id": parent.id, "status": "approved",
    })
    result = resolve_overrides([parent, child], [parent, child])
    assert result.rules == [parent, child]
    assert result.excluded == []
    assert result.relations == []


def test_a_broken_additional_override_prevents_partial_suppression():
    parent = guidance("R-SYNTHETIC-GENERAL")
    child = guidance("R-SYNTHETIC-LOCAL", ["synthetic-a"])
    relate(child, parent)
    child.relations.append({
        "type": "supersedes", "target_id": "R-SYNTHETIC-MISSING", "status": "approved",
    })
    result = resolve_overrides([parent, child], [parent, child])
    assert result.rules == [parent, child]
    assert result.excluded == result.relations == []
    assert result.issues[0]["reason"] == "missing_override_target"
