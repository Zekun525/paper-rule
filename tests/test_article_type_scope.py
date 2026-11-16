import pytest

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.retrieval.context import applies, build_context


@pytest.mark.parametrize(
    "venue,article_type,expected",
    [
        ("SYNTHETIC-JOURNAL", "full", True),
        ("SYNTHETIC-JOURNAL", "letter", False),
        ("SYNTHETIC-JOURNAL", "", False),
        ("OTHER-JOURNAL", "full", False),
    ],
)
def test_journal_and_article_type_are_independent_scope_requirements(venue, article_type, expected):
    rule = RuleRecord(
        id="R-SYNTHETIC-FULL",
        status="active",
        short_title="Synthetic full article structure",
        statement="Include the full article discussion structure.",
        scope=RuleScope(
            levels=["publication"],
            venues=["SYNTHETIC-JOURNAL"],
            article_types=["full"],
        ),
    )
    paper = PaperProfile(paper_id="synthetic-paper", venue=venue, article_type=article_type)
    assert applies(rule, paper)[0] is expected
    bundle = build_context([rule], paper)
    assert bool(bundle["rules"]) is expected


def test_unspecified_article_type_filter_does_not_exclude_letters():
    rule = RuleRecord(
        id="R-SYNTHETIC-ALL",
        status="active",
        short_title="Shared writing guidance",
        statement="Define symbols before use.",
        scope=RuleScope(levels=["publication"], venues=["SYNTHETIC-JOURNAL"]),
    )
    paper = PaperProfile(
        paper_id="synthetic-letter", venue="SYNTHETIC-JOURNAL", article_type="letter",
    )
    assert applies(rule, paper)[0] is True
