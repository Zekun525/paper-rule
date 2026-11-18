import json

import pytest

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.retrieval.context import build_context


def guidance(rule_id, target=None, status="approved", **changes):
    relations = []
    if target is not None:
        relation = {"type": "conflicts_with", "target_id": target}
        if status is not None:
            relation["status"] = status
        relations.append(relation)
    return RuleRecord(
        id=rule_id, short_title="Synthetic conflict guidance",
        statement=changes.pop("statement", "State synthetic assumptions."),
        status="active", relations=relations, **changes,
    )


def test_approved_conflicts_are_reported_once_without_changing_either_rule():
    rules = [guidance("R-SYNTHETIC-A", "R-SYNTHETIC-B"),
             guidance("R-SYNTHETIC-B", "R-SYNTHETIC-A")]
    original = [rule.model_dump_json() for rule in rules]
    bundle = build_context(rules, PaperProfile(paper_id="synthetic-paper"))
    assert len(bundle["rules"]) == 2
    assert bundle["complete"] is False
    assert bundle["unresolved_conflicts"] == [{
        "rule_ids": ["R-SYNTHETIC-A", "R-SYNTHETIC-B"],
        "rule_versions": {"R-SYNTHETIC-A": 1, "R-SYNTHETIC-B": 1},
        "reason": "approved_conflicting_rules",
    }]
    assert bundle["relation_issues"] == []
    assert [rule.model_dump_json() for rule in rules] == original


@pytest.mark.parametrize("status", ["candidate", None])
def test_candidate_relation_is_not_treated_as_an_approved_conflict(status):
    rules = [guidance("R-SYNTHETIC-A", "R-SYNTHETIC-B", status),
             guidance("R-SYNTHETIC-B")]
    bundle = build_context(rules, PaperProfile(paper_id="synthetic-paper"))
    assert len(bundle["rules"]) == 2
    assert bundle["complete"] is True
    assert bundle["unresolved_conflicts"] == []


def test_conflicts_are_detected_before_the_context_budget_can_hide_a_rule():
    rules = [guidance("R-SYNTHETIC-A", "R-SYNTHETIC-B"),
             guidance("R-SYNTHETIC-B")]
    bundle = build_context(rules, PaperProfile(paper_id="synthetic-paper"), max_rules=1)
    assert len(bundle["rules"]) == 1
    assert bundle["mandatory_omitted"] == []
    assert bundle["complete"] is False
    assert bundle["unresolved_conflicts"][0]["rule_ids"] == [
        "R-SYNTHETIC-A", "R-SYNTHETIC-B",
    ]


def test_other_paper_rule_does_not_create_a_current_conflict_or_expose_its_text():
    private = guidance(
        "R-SYNTHETIC-B", scope=RuleScope(paper_ids=["synthetic-other"]),
        statement="Synthetic unrelated rule text must remain outside this context.",
    )
    bundle = build_context(
        [guidance("R-SYNTHETIC-A", private.id), private],
        PaperProfile(paper_id="synthetic-paper"),
    )
    assert bundle["complete"] is True
    assert bundle["unresolved_conflicts"] == []
    assert private.statement not in json.dumps(bundle)


def test_inactive_target_does_not_create_an_active_conflict():
    inactive = guidance("R-SYNTHETIC-B")
    inactive.status = "deprecated"
    bundle = build_context(
        [guidance("R-SYNTHETIC-A", inactive.id), inactive],
        PaperProfile(paper_id="synthetic-paper"),
    )
    assert bundle["unresolved_conflicts"] == []
    assert bundle["complete"] is True


@pytest.mark.parametrize("target,reason", [
    ("R-SYNTHETIC-MISSING", "missing_conflict_target"),
    ("R-SYNTHETIC-A", "self_conflict"),
])
def test_broken_approved_conflict_relationship_requires_review(target, reason):
    bundle = build_context(
        [guidance("R-SYNTHETIC-A", target)], PaperProfile(paper_id="synthetic-paper"),
    )
    assert bundle["complete"] is False
    assert bundle["unresolved_conflicts"] == []
    assert bundle["relation_issues"] == [{
        "rule_id": "R-SYNTHETIC-A", "target_id": target, "reason": reason,
    }]
