from itertools import product

import pytest

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.retrieval.context import applies
from paperrule.retrieval.scope_subset import prove_scope_subset

CASES = [
    ({}, {}, True, False),
    ({"paper_ids": ["synthetic-a"]}, {}, True, True),
    ({"paper_ids": ["synthetic-a"]},
     {"paper_ids": ["synthetic-a", "synthetic-b"]}, True, True),
    ({"paper_ids": ["synthetic-a", "synthetic-b"]},
     {"paper_ids": ["synthetic-a"]}, False, False),
    ({}, {"paper_ids": ["synthetic-a"]}, False, False),
    ({"include": ["paper:synthetic-a"]},
     {"paper_ids": ["synthetic-a"]}, True, False),
    ({"venues": ["synthetic-v1"]},
     {"include": ["venue:synthetic-v1", "venue:synthetic-v2"]}, True, True),
    ({"include": ["venue:synthetic-v1"]},
     {"venues": ["synthetic-v1"]}, True, False),
    ({"sections": ["intro"]}, {"exclude": ["section:proof"]}, True, True),
    ({"paper_ids": ["synthetic-a"]}, {"exclude": ["paper:synthetic-b"]}, True, True),
    ({"paper_ids": ["synthetic-a"]}, {"exclude": ["synthetic-b"]}, False, False),
    ({"paper_ids": ["synthetic-a"], "sections": ["intro"]},
     {"exclude": ["synthetic-b"]}, True, True),
    ({"exclude": ["synthetic-b", "section:proof"]},
     {"exclude": ["synthetic-b"]}, True, True),
    ({"exclude": ["paper:synthetic-b"]},
     {"exclude": ["synthetic-b"]}, False, False),
    ({"paper_ids": ["synthetic-a"], "sections": ["intro"]},
     {"include": ["paper:synthetic-a", "synthetic-a"]}, True, True),
    ({"paper_ids": ["synthetic-a"], "include": ["paper:synthetic-b"]},
     {}, False, False),
    ({}, {"paper_ids": ["synthetic-a"], "include": ["paper:synthetic-b"]}, False, False),
    ({"include": ["synthetic-unknown:value"]}, {}, False, False),
    ({}, {"exclude": ["synthetic-unknown:value"]}, False, False),
    ({"include": [""]}, {}, False, False),
    ({"venues": ["synthetic-v1", "synthetic-v1"]},
     {"venues": ["synthetic-v1"]}, True, False),
    ({"paper_ids": ["synthetic-a"], "task_types": ["review"]},
     {"paper_ids": ["synthetic-a"]}, True, True),
    ({"research_types": ["theory"]}, {"research_types": ["experiment"]}, False, False),
    ({"article_types": ["Letter"]}, {"article_types": ["Full", "Letter"]}, True, True),
]


@pytest.mark.parametrize(
    "child_data,parent_data,contained,strict", CASES,
    ids=[f"synthetic-scope-{index}" for index in range(len(CASES))],
)
def test_containment_matches_structured_scope_behavior(child_data, parent_data, contained, strict):
    child, parent = RuleScope(**child_data), RuleScope(**parent_data)
    original = child.model_dump(mode="json"), parent.model_dump(mode="json")
    result = prove_scope_subset(child, parent)
    assert result[:2] == (contained, strict)
    assert (child.model_dump(mode="json"), parent.model_dump(mode="json")) == original
    if not contained:
        return
    child_rule = RuleRecord(
        id="R-SYNTHETIC-CHILD", short_title="Synthetic child",
        statement="Synthetic guidance.", scope=child,
    )
    parent_rule = RuleRecord(
        id="R-SYNTHETIC-PARENT", short_title="Synthetic parent",
        statement="Synthetic guidance.", scope=parent,
    )
    # Exercise the independent application predicate across varying profiles,
    # including a section that exposes legacy paper-or-section exclusions.
    for paper_id, venue, section, task, research, article in product(
        ["synthetic-a", "synthetic-b", "synthetic-c"],
        ["synthetic-v1", "synthetic-v2", "synthetic-v3"],
        ["intro", "proof", "synthetic-b"], ["review", "edit"],
        ["theory", "experiment"], ["Full", "Letter"],
    ):
        profile = PaperProfile(
            paper_id=paper_id, venue=venue, research_type=research, article_type=article,
        )
        if applies(child_rule, profile, section, task)[0]:
            assert applies(parent_rule, profile, section, task)[0]


@pytest.mark.parametrize("child,parent,expected", [
    ({"effective_from": "2010-01-01T00:00:00Z"},
     {"effective_from": "2000-01-01T00:00:00Z"}, (True, True)),
    ({}, {"effective_from": "2000-01-01T00:00:00Z"}, (False, False)),
    ({"effective_from": "2000-01-01T00:00:00"},
     {"effective_from": "2000-01-01T00:00:00Z"}, (True, False)),
    ({"paper_ids": ["synthetic-a"], "exceptions": ["Synthetic condition."]},
     {"exceptions": ["Synthetic condition."]}, (True, True)),
    ({"exceptions": ["Synthetic condition."]}, {}, (False, False)),
    ({}, {"exceptions": ["Synthetic condition."]}, (False, False)),
    ({"effective_from": "0001-01-01T00:00:00+14:00"}, {}, (False, False)),
], ids=[
    "later-start", "missing-start", "naive-utc", "same-exception",
    "added-exception-unproven", "removed-exception-unproven", "unrepresentable-utc",
])
def test_temporal_and_free_text_conditions_are_conservative(child, parent, expected):
    assert prove_scope_subset(RuleScope(**child), RuleScope(**parent))[:2] == expected
