"""Apply bounded semantic checks to a previously captured manuscript rule snapshot."""
from __future__ import annotations

from hashlib import sha256

from paperrule.domain.models import RuleRecord, SemanticReviewEvidence, digest
from paperrule.providers import ProviderUnavailable
from paperrule.providers.base import AIProvider
from paperrule.review.manuscript_semantic import (
    MAX_INPUT_CHARS,
    PROMPT_VERSION,
    evaluate_manuscript_excerpt,
)


def augment_semantic_review(
    payload: dict, documents: list[dict], rules: list[RuleRecord],
    provider: AIProvider | None, *, max_calls: int = 8,
    blocked: dict[str, str] | None = None,
) -> None:
    if type(max_calls) is not int or max_calls not in range(1, 33):
        raise ValueError("Semantic request limit must be between 1 and 32")
    if len(documents) > 32:
        raise ValueError("Split semantic review into at most 32 text files per request")
    blocked = blocked or {}
    selected = [rule for rule in rules
                if rule.check_method == "semantic" or rule.scope.exceptions]
    selected_ids = {rule.id for rule in selected}
    payload["unavailable"] = [
        row for row in payload["unavailable"] if row["rule_id"] not in selected_ids
    ]
    # Phrase hits alone cannot decide whether an approved exception applies.
    exception_ids = {rule.id for rule in selected if rule.scope.exceptions}
    payload["findings"] = [
        row for row in payload["findings"] if row["rule_id"] not in exception_ids
    ]
    payload["semantic_evidence"] = []
    payload.setdefault("unresolved", [])
    coverage = {row["rule_id"]: row for row in payload["coverage"]}
    attempted = 0

    for rule in selected:
        errors = []
        reviewed_lines = 0
        had_input = False
        for document in documents:
            text = document["text"]
            lines = text.splitlines()
            targets = (set(document.get("changed_lines", set()))
                       if payload["diff_mode"] else set(range(1, len(lines) + 1)))
            if not targets:
                continue
            had_input = True
            entry = {
                "rule_id": rule.id, "rule_version": rule.version,
                "file_path": document["path"], "file_sha256": document["sha256"],
                "provider": provider.name if provider is not None else "manual",
                "model": "", "prompt_version": PROMPT_VERSION,
                "rule_sha256": digest(rule),
                "input_sha256": sha256(text.encode("utf-8")).hexdigest(),
                "selection": {
                    "mode": "changed_lines" if payload["diff_mode"] else "full_text",
                    "selected_line_count": len(targets),
                },
                "status": "unavailable", "checked_line_count": 0,
                "judgment": {}, "findings": [], "human_review": "pending",
                "formal_proof_status": "not_performed", "error": None,
            }
            reason = blocked.get(rule.id, "")
            if not reason and (provider is None or provider.name == "fake"):
                reason = "semantic_provider_unavailable"
            if not reason and (
                not text.strip() or len(text) > MAX_INPUT_CHARS
                or len(rule.model_dump_json()) > 24000
            ):
                reason = "semantic_input_unavailable"
            if not reason and attempted >= max_calls:
                reason = "semantic_call_budget_exceeded"
            if not reason:
                attempted += 1
                try:
                    evaluated = evaluate_manuscript_excerpt(
                        text, rule, provider, path=document["path"],
                        section=payload["section"], task=payload["task"],
                        changed_lines=targets if payload["diff_mode"] else None,
                    )
                    entry.update(evaluated)
                    if evaluated["status"] not in {"checked", "findings"}:
                        reason = "semantic_judgment_uncertain"
                    reviewed_lines += evaluated["checked_line_count"]
                    payload["findings"].extend(evaluated["findings"])
                    for question in evaluated["judgment"]["unresolved"]:
                        payload["unresolved"].append(rule.id + ": " + question)
                    if evaluated["status"] == "not_reviewed":
                        payload["unresolved"].append(
                            rule.id + ": " + evaluated["judgment"]["explanation"]
                        )
                except ProviderUnavailable as error:
                    reason = "provider_" + error.code
                    if error.http_status is not None:
                        reason += "_" + str(error.http_status)
                except ValueError:
                    reason = "semantic_response_invalid"
            if reason:
                entry["error"] = reason
                errors.append(reason)
            payload["semantic_evidence"].append(
                SemanticReviewEvidence.model_validate(entry).model_dump(mode="json")
            )
        row = coverage[rule.id]
        if not had_input:
            row.update(status="not_reviewed", checked_line_count=0,
                       reason="no_lines_in_selected_input")
        elif errors:
            row.update(status="unavailable", checked_line_count=0, reason=errors[0])
            payload["unavailable"].append({
                "rule_id": rule.id, "rule_version": rule.version, "reason": errors[0],
            })
        else:
            row.update(status="checked", checked_line_count=reviewed_lines,
                       reason="semantic_review")

    for rule_id, reason in blocked.items():
        if rule_id in coverage:
            coverage[rule_id].update(
                status="unavailable", checked_line_count=0, reason=reason,
            )
            if not any(row["rule_id"] == rule_id for row in payload["unavailable"]):
                payload["unavailable"].append({
                    "rule_id": rule_id, "rule_version": coverage[rule_id]["rule_version"],
                    "reason": reason,
                })
            payload["unresolved"].append(
                rule_id + ": 存在尚未解决的规则关系，请核对后重新审查。"
            )
    records = payload["semantic_evidence"]
    completed = [row for row in records if row["status"] in {"checked", "findings"}]
    payload["semantic_status"] = (
        "not_reviewed" if not completed
        else "incomplete" if any(row["status"] not in {"checked", "findings"}
                                 for row in records) or blocked
        else "reviewed"
    )
    if completed:
        payload["provider"] = "+".join(sorted(
            {"deterministic"} | {row["provider"] for row in completed}
        ))
        payload["model"] = ", ".join(sorted({row["model"] for row in completed}))
    if not any(row["status"] == "checked" for row in payload["coverage"]):
        payload["status"] = "not_reviewed" if not payload["findings"] else "incomplete"
    elif payload["unavailable"] or any(
        row["status"] != "checked" for row in payload["coverage"]
    ):
        payload["status"] = "incomplete"
    else:
        payload["status"] = "findings" if payload["findings"] else "checked"
