from paperrule.domain.models import RegressionCase, RuleRecord
from paperrule.providers.base import FakeProvider
from paperrule.review.regression import run_cases


def test_fake_provider_is_explicitly_offline():
    response = FakeProvider().chat([{"role": "user", "content": "hello"}])
    assert response.provider == "fake" and "离线" in response.text

def test_regression_detects_exact_avoid_rule():
    rule = RuleRecord(id="G-1", status="active", short_title="Avoid vague", statement="avoid: very clearly", check_method="deterministic")
    report = run_cases([RegressionCase(id="R-1", rule_id="G-1", input_text="This is very clearly true.", expected="violation")], [rule])
    assert report["passed"] == 1
