"""Offline contract tests; scripted responses do not establish model quality."""
import json
from hashlib import sha256

import pytest

from paperrule.domain.models import RuleRecord, RuleStatus, digest
from paperrule.providers import AIResponse, ProviderUnavailable
from paperrule.providers.base import AIProvider
from paperrule.review.manuscript_semantic import evaluate_manuscript_excerpt

TEXT = chr(10).join([
    "Synthetic context.",
    "Synthetic unsupported claim.",
    "Synthetic conclusion.",
])


class ScriptedProvider(AIProvider):
    name = "synthetic-unit-provider"

    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def chat(self, messages, *, timeout=30):
        assert timeout == 30
        self.calls.append(messages)
        return AIResponse(
            text=json.dumps(self.payload), provider=self.name,
            model="synthetic-unit-model",
        )


@pytest.fixture(autouse=True)
def no_real_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture
def rule():
    return RuleRecord(
        id="R-SYNTHETIC-MANUSCRIPT", status="active",
        short_title="Explain synthetic assumptions",
        statement="Explain the assumptions supporting a synthetic inference.",
    )


def judgment(rule, verdict="violation"):
    return {
        "rule_id": rule.id, "rule_version": rule.version,
        "verdict": verdict, "explanation": "Synthetic scripted judgment.",
        "findings": [{
            "line": 2, "quote": "Synthetic unsupported claim.",
            "explanation": "Synthetic assumption was not explained.",
            "recommendation": "State the synthetic assumption and explain the inference.",
        }] if verdict == "violation" else [],
        "unresolved": [],
    }


def test_semantic_findings_bind_rule_text_selection_and_original_line(rule):
    provider = ScriptedProvider(judgment(rule))
    result = evaluate_manuscript_excerpt(
        TEXT, rule, provider, path="synthetic.tex", changed_lines={2},
    )
    assert result["status"] == "findings"
    assert result["checked_line_count"] == 1
    assert result["selection"] == {"mode": "changed_lines", "line_numbers": [2]}
    assert result["rule_sha256"] == digest(rule)
    assert result["input_sha256"] == sha256(TEXT.encode("utf-8")).hexdigest()
    assert result["prompt_version"] == "manuscript-semantic-v1"
    assert result["human_review"] == "pending"
    assert result["formal_proof_status"] == "not_performed"
    assert len(result["findings"]) == 1
    finding = result["findings"][0]
    assert finding["rule_id"] == rule.id and finding["rule_version"] == rule.version
    assert finding["location"] == "synthetic.tex:2"
    assert finding["quote"] == "Synthetic unsupported claim."
    assert finding["review_type"] == "semantic"
    assert finding["confirmed"] is None
    assert len(provider.calls) == 1
    sent = json.loads(provider.calls[0][-1]["content"])
    assert sent["excerpt"] == TEXT
    assert sent["selected_lines"] == [2]
    assert "not formal proof" in provider.calls[0][0]["content"]


@pytest.mark.parametrize("failure", [
    "wrong-rule", "wrong-version", "invented-quote", "wrong-line",
    "outside-selected-lines", "compliant-findings", "uncertain-findings",
    "empty-violation",
])
def test_invalid_findings_are_not_accepted(rule, failure):
    payload = judgment(rule)
    if failure == "wrong-rule":
        payload["rule_id"] = "R-SYNTHETIC-OTHER"
    elif failure == "wrong-version":
        payload["rule_version"] = rule.version + 1
    elif failure == "invented-quote":
        payload["findings"][0]["quote"] = "Synthetic text absent from the manuscript."
    elif failure == "wrong-line":
        payload["findings"][0]["line"] = 3
    elif failure == "outside-selected-lines":
        payload["findings"][0].update(line=1, quote="Synthetic context.")
    elif failure == "compliant-findings":
        payload["verdict"] = "compliant"
    elif failure == "uncertain-findings":
        payload["verdict"] = "uncertain"
    else:
        payload["findings"] = []
    provider = ScriptedProvider(payload)
    with pytest.raises(ValueError):
        evaluate_manuscript_excerpt(
            TEXT, rule, provider, path="synthetic.tex", changed_lines={2},
        )
    assert len(provider.calls) == 1


def test_uncertainty_does_not_claim_checked_lines(rule):
    payload = judgment(rule, "uncertain")
    payload["unresolved"] = ["The synthetic assumption needs more context."]
    result = evaluate_manuscript_excerpt(
        TEXT, rule, ScriptedProvider(payload), path="synthetic.tex",
    )
    assert result["status"] == "not_reviewed"
    assert result["checked_line_count"] == 0
    assert result["findings"] == []
    assert result["judgment"]["unresolved"] == payload["unresolved"]
    assert result["human_review"] == "pending"
    assert result["formal_proof_status"] == "not_performed"


def test_unresolved_compliant_reply_remains_incomplete(rule):
    payload = judgment(rule, "compliant")
    payload["unresolved"] = ["A synthetic definition is still unclear."]
    result = evaluate_manuscript_excerpt(
        TEXT, rule, ScriptedProvider(payload), path="synthetic.tex",
    )
    assert result["status"] == "incomplete"
    assert result["checked_line_count"] == 0
    assert result["findings"] == []


def test_compliant_reply_is_limited_to_the_recorded_selection(rule):
    result = evaluate_manuscript_excerpt(
        TEXT, rule, ScriptedProvider(judgment(rule, "compliant")),
        path="synthetic.tex", changed_lines={2},
    )
    assert result["status"] == "checked"
    assert result["checked_line_count"] == 1
    assert result["selection"]["line_numbers"] == [2]
    assert result["human_review"] == "pending"
    assert result["formal_proof_status"] == "not_performed"


@pytest.mark.parametrize("selected", [set(), {0}, {4}, {True}],
                         ids=["empty", "zero", "outside-input", "boolean"])
def test_invalid_selection_is_rejected_before_model_request(rule, selected):
    provider = ScriptedProvider(judgment(rule))
    with pytest.raises(ValueError, match="selected_lines"):
        evaluate_manuscript_excerpt(
            TEXT, rule, provider, path="synthetic.tex", changed_lines=selected,
        )
    assert provider.calls == []


def test_fake_provider_is_not_a_semantic_review(rule):
    provider = ScriptedProvider(judgment(rule))
    provider.name = "fake"
    with pytest.raises(ProviderUnavailable):
        evaluate_manuscript_excerpt(TEXT, rule, provider, path="synthetic.tex")
    assert provider.calls == []


def test_inactive_rule_is_rejected_before_model_request(rule):
    provider = ScriptedProvider(judgment(rule))
    inactive = rule.model_copy(update={"status": RuleStatus.PROPOSED})
    with pytest.raises(ValueError, match="rule_not_active"):
        evaluate_manuscript_excerpt(TEXT, inactive, provider, path="synthetic.tex")
    assert provider.calls == []


def test_oversized_excerpt_is_not_sent_to_the_model(rule):
    provider = ScriptedProvider(judgment(rule))
    with pytest.raises(ValueError, match="input_too_large"):
        evaluate_manuscript_excerpt("x" * 100001, rule, provider, path="synthetic.tex")
    assert provider.calls == []


def test_multiline_quote_can_intersect_a_selected_changed_line(rule):
    payload = judgment(rule)
    payload["findings"][0].update(
        line=1, quote="Synthetic context." + chr(10) + "Synthetic unsupported claim.",
    )
    result = evaluate_manuscript_excerpt(
        TEXT, rule, ScriptedProvider(payload), path="synthetic.tex", changed_lines={2},
    )
    assert result["findings"][0]["location"] == "synthetic.tex:1-2"
    assert result["findings"][0]["quote"] in TEXT
    assert result["checked_line_count"] == 1
