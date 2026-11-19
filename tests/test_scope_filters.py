import hashlib
import json

import pytest

from paperrule.domain.models import (
    PaperProfile,
    RegressionCase,
    RuleRecord,
    RuleScope,
    RuleStatus,
)
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import applies, build_context
from paperrule.retrieval.scope_filters import UNRESOLVED_SCOPE
from paperrule.review.files import check_documents
from paperrule.review.regression import run_cases


def profile(**changes):
    data = {
        "paper_id": "SYNTHETIC-A", "research_type": "theory",
        "venue": "SYNTHETIC-TIT", "article_type": "full",
    }
    data.update(changes)
    return PaperProfile(**data)


def guidance(**scope):
    return RuleRecord(
        id="G-SYNTHETIC-FILTER", status="active", short_title="Synthetic filter",
        statement="avoid: synthetic target", check_method="deterministic",
        scope=RuleScope(**scope),
    )


def test_include_groups_are_intersections_with_alternatives_inside_each_field():
    rule = guidance(include=[
        "paper:SYNTHETIC-A", "venue:SYNTHETIC-TIT",
        "venue:SYNTHETIC-TWC", "section:Proof", "task:proof_rewrite",
    ])
    assert applies(rule, profile(), "Proof", "proof_rewrite")[0]
    assert applies(rule, profile(venue="SYNTHETIC-TWC"), "Proof", "proof_rewrite")[0]
    assert not applies(rule, profile(), "Introduction", "proof_rewrite")[0]
    assert not applies(rule, profile(), "Proof", "review")[0]
    assert not applies(rule, profile(venue="OTHER"), "Proof", "proof_rewrite")[0]
    other = profile(paper_id="SYNTHETIC-B")
    bundle = build_context([rule], other, "Proof", "proof_rewrite")
    assert bundle["rules"] == []
    assert rule.statement not in json.dumps(bundle)


@pytest.mark.parametrize("selector", [
    "paper:SYNTHETIC-A", "research_type:theory", "venue:SYNTHETIC-TIT",
    "article_type:full", "section:Proof", "task:proof_rewrite",
    "SYNTHETIC-A", "Proof",
])
def test_exclude_matches_any_selector_and_preserves_legacy_values(selector):
    assert applies(guidance(exclude=[selector]), profile(), "Proof", "proof_rewrite") == (
        False, "explicitly excluded",
    )


def test_bare_include_values_are_paper_ids_and_do_not_match_unrelated_sections():
    rule = guidance(include=["SYNTHETIC-A"])
    assert applies(rule, profile(), "Proof")[0]
    assert not applies(rule, profile(paper_id="SYNTHETIC-B"), "SYNTHETIC-A")[0]


def test_existing_scope_fields_still_narrow_include_filters():
    rule = guidance(paper_ids=["SYNTHETIC-A"], include=["venue:SYNTHETIC-TIT"])
    assert not applies(rule, profile(paper_id="SYNTHETIC-B"))[0]
    assert not applies(rule, profile(venue="OTHER"))[0]
    assert applies(rule, profile())[0]


@pytest.mark.parametrize("scope", [
    {"include": ["unknown:value"]}, {"exclude": ["unknown:value"]},
    {"include": ["paper:"]},
], ids=["unknown-include", "unknown-exclude", "empty-value"])
def test_unresolved_filters_make_context_incomplete_without_exposing_rule_text(scope):
    rule = guidance(**scope)
    bundle = build_context([rule], profile())
    assert applies(rule, profile()) == (False, UNRESOLVED_SCOPE)
    assert bundle["rules"] == []
    assert bundle["complete"] is False
    assert bundle["scope_issues"] == [{"rule_id": rule.id, "reason": UNRESOLVED_SCOPE}]
    assert rule.statement not in json.dumps(bundle)


def test_other_paper_is_excluded_before_unresolved_conditions_are_reported():
    rule = guidance(paper_ids=["OTHER"], include=["unknown:value"])
    bundle = build_context([rule], profile())
    assert bundle["complete"] is True
    assert bundle["scope_issues"] == []
    assert rule.statement not in json.dumps(bundle)


def test_selector_prefixes_trim_whitespace_but_values_remain_case_sensitive():
    assert applies(guidance(include=[" SECTION : Proof "]), profile(), "Proof")[0]
    assert not applies(guidance(include=["section:proof"]), profile(), "Proof")[0]


def test_unresolved_scope_is_not_silently_reported_as_checked(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    paper = profile()
    store.save_paper(paper)
    gov = Governance(store)
    draft = guidance(include=["unknown:value"]).model_copy(update={"status": RuleStatus.PROPOSED})
    proposal = gov.propose(draft)
    gov.approve(proposal.proposal_id, proposal.proposal_hash, actor="synthetic-test")
    text = "synthetic target"
    report = check_documents(store, [{
        "path": "synthetic.txt", "text": text, "changed_lines": set(),
        "sha256": hashlib.sha256(text.encode()).hexdigest(), "diff": "",
    }], paper)
    assert report["status"] == "not_reviewed"
    assert report["findings"] == []
    assert report["unavailable"] == [{
        "rule_id": draft.id, "rule_version": 1, "reason": "scope_condition_unresolved",
    }]
    assert draft.statement not in json.dumps(report)


def test_regression_with_explicit_filters_requires_a_profile():
    rule = guidance(include=["paper:SYNTHETIC-A"])
    case = RegressionCase(
        id="CASE-SYNTHETIC-FILTER", rule_id=rule.id,
        input_text="synthetic target", expected="violation",
    )
    report = run_cases([case], [rule])
    assert report["status"] == "incomplete"
    assert report["results"][0]["reason"] == "scope_profile_unavailable"
    assert report["results"][0]["passed"] is None
