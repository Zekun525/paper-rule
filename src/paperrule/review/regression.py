from __future__ import annotations

from uuid import uuid4

from paperrule.domain.models import PaperProfile, RegressionCase, RuleRecord, utcnow
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import applies
from paperrule.review.check import check_text
from paperrule.sync.git import GitSync


def run_cases(cases: list[RegressionCase], rules: list[RuleRecord],
              profile: PaperProfile | None = None) -> dict:
    results = []
    violations = {"violation", "identify_violation"}
    clean = {"clean", "no_violation", "non_violation", "compliant"}
    for case in cases:
        rule = next((r for r in rules if r.id == case.rule_id), None)
        reason = ""
        if case.expected not in violations | clean:
            reason = "unknown_expected_behavior"
        elif rule is None:
            reason = "rule_not_found"
        elif rule.status.value != "active":
            reason = "rule_not_active"
        elif case.rule_version is not None and case.rule_version != rule.version:
            reason = "rule_version_mismatch"
        elif profile and not applies(rule, profile, case.section, case.task)[0]:
            reason = "rule_outside_scope"
        elif case.check_method == "semantic" or rule.check_method == "semantic":
            reason = "semantic_provider_unavailable"
        elif rule.check_method != "deterministic" or not rule.statement.casefold().startswith("avoid: "):
            reason = "deterministic_check_not_supported"
        if reason:
            results.append({
                "id": case.id, "rule_id": case.rule_id, "passed": None,
                "detected": None, "status": "unavailable", "reason": reason,
                "expected_behavior": case.expected, "findings": [],
            })
            continue
        findings = check_text(case.input_text, [rule])
        detected = bool(findings)
        expected = case.expected in violations
        results.append({
            "id": case.id, "rule_id": case.rule_id, "rule_version": rule.version,
            "passed": detected == expected, "status": "passed" if detected == expected else "failed",
            "detected": detected, "expected": expected, "expected_behavior": case.expected,
            "findings": [finding.model_dump(mode="json") for finding in findings],
        })
    passed = sum(r["passed"] is True for r in results)
    failed = sum(r["passed"] is False for r in results)
    unavailable = sum(r["passed"] is None for r in results)
    status = "incomplete" if unavailable else "failed" if failed else "passed" if results else "empty"
    return {"total": len(results), "passed": passed, "failed": failed,
            "unavailable": unavailable, "status": status, "results": results}


def run_stored_cases(store: MemoryStore, paper_id: str = "") -> dict:
    with store.locked():
        profile = next((p for p in store.papers() if p.paper_id == paper_id), None)
        if paper_id and profile is None:
            raise ValueError("Paper profile was not found")
        cases = [case for case in store.regressions()
                 if not paper_id or case.paper_id in {None, paper_id}]
        report = run_cases(cases, store.rules(), profile)
        report.update({
            "run_id": "RUN-" + uuid4().hex,
            "created_at": utcnow().isoformat(), "paper_id": paper_id or None,
            "memory_commit": GitSync(store.root).head() or None,
        })
        store.write_json("runs", report["run_id"], report)
        return report


def reports(store: MemoryStore) -> list[dict]:
    return sorted(store.read_json("runs"), key=lambda item: item["created_at"], reverse=True)
