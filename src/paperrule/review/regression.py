from __future__ import annotations

import os
from uuid import uuid4

from paperrule.domain.models import PaperProfile, RegressionCase, RuleRecord, digest, utcnow
from paperrule.persistence.store import MemoryStore
from paperrule.providers import CodexCLIProvider, OpenAIAPIProvider, ProviderUnavailable
from paperrule.providers.base import AIProvider
from paperrule.retrieval.context import applies
from paperrule.review.check import check_text
from paperrule.review.semantic import evaluate
from paperrule.sync.git import GitSync


def run_cases(cases: list[RegressionCase], rules: list[RuleRecord],
              profile: PaperProfile | None = None, *, provider: AIProvider | None = None) -> dict:
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
        elif (case.check_method == "semantic" or rule.check_method == "semantic") and (
            provider is None or provider.name == "fake"
        ):
            reason = "semantic_provider_unavailable"
        elif case.check_method != "semantic" and rule.check_method != "semantic" and (
            rule.check_method != "deterministic" or not rule.statement.casefold().startswith("avoid: ")
        ):
            reason = "deterministic_check_not_supported"
        evidence = {
            "case_sha256": digest(case), "input_sha256": digest(case.input_text),
            "rule_sha256": digest(rule) if rule else None,
            "case_snapshot": case.model_dump(mode="json"),
            "rule_snapshot": rule.model_dump(mode="json") if rule else None,
            "human_review": "pending",
        }
        semantic = {}
        if not reason and (case.check_method == "semantic" or rule.check_method == "semantic"):
            try:
                semantic = evaluate(case, rule, provider)
                if semantic["judgment"]["verdict"] == "uncertain":
                    reason = "semantic_judgment_uncertain"
            except ProviderUnavailable:
                reason = "semantic_provider_unavailable"
            except ValueError:
                reason = "semantic_response_invalid"
        if reason:
            results.append({
                **evidence, **semantic,
                "id": case.id, "rule_id": case.rule_id, "passed": None,
                "detected": None, "status": "unavailable", "reason": reason,
                "expected_behavior": case.expected, "findings": [],
            })
            continue
        findings = check_text(case.input_text, [rule]) if not semantic else []
        detected = semantic["judgment"]["detected"] if semantic else bool(findings)
        expected = case.expected in violations
        results.append({
            **evidence, **semantic,
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
        rules = store.rules()
        memory_commit = GitSync(store.root).head() if (store.root / ".git").exists() else None
    # Snapshot under lock, but never hold up approvals while waiting for a model.
    factories = {
        "codex": CodexCLIProvider, "codex_cli": CodexCLIProvider,
        "openai": OpenAIAPIProvider, "openai_api": OpenAIAPIProvider,
    }
    factory = factories.get(os.environ.get("PAPERRULE_PROVIDER", "manual").casefold())
    report = run_cases(cases, rules, profile, provider=factory() if factory else None)
    with store.locked():
        report.update({
            "run_id": "RUN-" + uuid4().hex,
            "created_at": utcnow().isoformat(), "paper_id": paper_id or None,
            "memory_commit": memory_commit,
        })
        store.write_json("runs", report["run_id"], report)
        return report


def reports(store: MemoryStore) -> list[dict]:
    return sorted(store.read_json("runs"), key=lambda item: item["created_at"], reverse=True)
