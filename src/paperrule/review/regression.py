from __future__ import annotations

from paperrule.domain.models import RegressionCase, RuleRecord
from paperrule.review.check import check_text


def run_cases(cases: list[RegressionCase], rules: list[RuleRecord]) -> dict:
    results = []
    for case in cases:
        findings = check_text(case.input_text, [r for r in rules if r.id == case.rule_id])
        detected = bool(findings)
        expected = case.expected in {"violation", "identify_violation"}
        results.append({"id": case.id, "passed": detected == expected, "detected": detected, "expected": expected})
    return {"total": len(results), "passed": sum(r["passed"] for r in results), "failed": sum(not r["passed"] for r in results), "results": results}
