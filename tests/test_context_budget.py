import json
from datetime import UTC, datetime, timedelta

import pytest

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.retrieval.context import applies, build_context


def rule(identifier, **changes):
    return RuleRecord(
        id=identifier, short_title="Synthetic guidance",
        statement=changes.pop("statement", "Explain the synthetic assumptions."),
        status="active", **changes,
    )


def test_500_rules_do_not_evict_mandatory_global_and_paper_guidance():
    rules = [rule(f"R-SYNTHETIC-{index:03}") for index in range(498)]
    rules += [
        rule("R-SYNTHETIC-MANDATORY", blocking=True),
        rule("R-SYNTHETIC-PAPER", scope=RuleScope(
            paper_ids=["synthetic-paper"], sections=["proof"], task_types=["revise"],
        )),
    ]
    bundle = build_context(
        rules, PaperProfile(paper_id="synthetic-paper"), "proof", "revise", max_rules=7,
    )
    identifiers = {entry["rule"]["id"] for entry in bundle["rules"]}
    assert len(bundle["rules"]) == 7
    assert {"R-SYNTHETIC-MANDATORY", "R-SYNTHETIC-PAPER"}.issubset(identifiers)
    assert bundle["complete"] is True
    assert bundle["mandatory_omitted"] == []
    assert len(bundle["excluded_rules"]) == 493
    assert all(entry["why_loaded"] for entry in bundle["rules"])


def test_rule_character_budget_matches_compact_serialized_rules():
    bundle = build_context(
        [rule(f"R-SYNTHETIC-{index}") for index in range(10)],
        PaperProfile(paper_id="synthetic-paper"), max_rule_chars=3000,
    )
    serialized = json.dumps(bundle["rules"], ensure_ascii=False, separators=(",", ":"))
    assert len(serialized) == bundle["budget"]["used_rule_chars"]
    assert 3000 >= len(serialized)
    assert 10 > len(bundle["rules"]) > 0


def test_oversized_mandatory_rule_is_explicitly_incomplete_without_truncating_statement():
    guidance = rule("R-SYNTHETIC-LARGE", blocking=True, statement="Synthetic guidance. " * 500)
    bundle = build_context(
        [guidance], PaperProfile(paper_id="synthetic-paper"), max_rule_chars=1000,
    )
    assert bundle["rules"] == []
    assert bundle["complete"] is False
    assert bundle["mandatory_omitted"] == [guidance.id]
    assert bundle["excluded_rules"] == [{
        "rule_id": guidance.id, "reason": "context budget exceeded",
    }]
    assert bundle["budget"]["used_rule_chars"] == 2


def test_unrelated_paper_rule_text_is_not_included_in_diagnostics():
    private = rule(
        "R-SYNTHETIC-OTHER",
        statement="Synthetic unrelated paper text must stay outside this context.",
        scope=RuleScope(paper_ids=["synthetic-other"]),
    )
    bundle = build_context([private], PaperProfile(paper_id="synthetic-paper"))
    assert bundle["rules"] == []
    assert private.statement not in json.dumps(bundle, ensure_ascii=False)
    assert bundle["excluded_rules"] == [{
        "rule_id": private.id, "reason": "different paper",
    }]


def test_exact_duplicate_is_loaded_once():
    guidance = rule("R-SYNTHETIC-DUPLICATE")
    bundle = build_context(
        [guidance, guidance.model_copy(deep=True)], PaperProfile(paper_id="synthetic-paper"),
    )
    assert len(bundle["rules"]) == 1
    assert bundle["excluded_rules"] == [{
        "rule_id": guidance.id, "reason": "duplicate identifier",
    }]


@pytest.mark.parametrize("timezone_aware", [True, False])
def test_future_effective_rule_is_not_loaded(timezone_aware):
    future = datetime.now(UTC) + timedelta(days=1)
    if not timezone_aware:
        future = future.replace(tzinfo=None)
    guidance = rule("R-SYNTHETIC-FUTURE", scope=RuleScope(effective_from=future))
    paper = PaperProfile(paper_id="synthetic-paper")
    assert applies(guidance, paper) == (False, "rule is not effective yet")
    bundle = build_context([guidance], paper)
    assert bundle["rules"] == []
    assert bundle["excluded_rules"][0]["reason"] == "rule is not effective yet"


@pytest.mark.parametrize("budgets", [{"max_rules": 0}, {"max_rule_chars": 1}])
def test_invalid_context_budget_is_rejected(budgets):
    with pytest.raises(ValueError, match="budgets"):
        build_context([], PaperProfile(paper_id="synthetic-paper"), **budgets)
