import json

import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import RegressionCase, RuleRecord, digest
from paperrule.persistence.store import MemoryStore
from paperrule.providers import ProviderUnavailable
from paperrule.providers.base import AIProvider, AIResponse, FakeProvider
from paperrule.review.regression import run_cases


class ScriptedJudge(AIProvider):
    name = "scripted-test"

    def __init__(self, reply):
        self.reply = reply
        self.messages = []

    def chat(self, messages, *, timeout=30):
        self.messages = messages
        assert timeout == 30
        if isinstance(self.reply, Exception):
            raise self.reply
        text = self.reply if isinstance(self.reply, str) else json.dumps(self.reply)
        return AIResponse(text=text, provider=self.name, model="synthetic-model")


def inputs():
    rule = RuleRecord(id="R-synthetic", status="active", short_title="Define symbols",
                      statement="Define each symbol before using it.", check_method="semantic")
    case = RegressionCase(id="RT-synthetic", rule_id=rule.id,
                          input_text="The value of x increases.", expected="violation",
                          explanation="SECRET_EXPECTED_RATIONALE", check_method="semantic")
    reply = {"rule_id": rule.id, "rule_version": 1, "verdict": "violation",
             "detected": True, "explanation": "The excerpt does not define x.", "quote": "x"}
    return rule, case, reply


def test_semantic_result_has_bound_evidence_and_no_answer_leak():
    rule, case, reply = inputs()
    judge = ScriptedJudge(reply)
    report = run_cases([case], [rule], provider=judge)
    assert report["passed"] == 1
    result = report["results"][0]
    assert result["judgment"] == reply
    assert result["provider"] == judge.name
    assert result["model"] == "synthetic-model"
    assert result["prompt_version"] == "regression-semantic-v1"
    assert result["input_sha256"] == digest(case.input_text)
    assert result["rule_sha256"] == digest(rule)
    assert result["case_snapshot"] == case.model_dump(mode="json")
    assert result["human_review"] == "pending"
    data = json.loads(judge.messages[-1]["content"])
    assert "expected" not in data
    assert "SECRET_EXPECTED_RATIONALE" not in json.dumps(judge.messages)
    assert data["excerpt"] == case.input_text


@pytest.mark.parametrize("patch", [
    {"rule_id": "R-other"}, {"rule_version": 2}, {"quote": "invented evidence"},
    {"quote": ""}, {"detected": "true"}, {"detected": False},
    {"verdict": "compliant"}, {"verdict": "uncertain"},
    {"extra_command": "execute"}, {"explanation": ""},
])
def test_invalid_semantic_answers_never_pass(patch):
    rule, case, reply = inputs()
    reply.update(patch)
    report = run_cases([case], [rule], provider=ScriptedJudge(reply))
    assert report["passed"] == 0
    assert report["failed"] == 0
    assert report["results"][0]["reason"] == "semantic_response_invalid"


@pytest.mark.parametrize("reply", ["not json", ProviderUnavailable("synthetic outage")])
def test_provider_errors_are_incomplete(reply):
    rule, case, _ = inputs()
    report = run_cases([case], [rule], provider=ScriptedJudge(reply))
    assert report["status"] == "incomplete"
    assert report["unavailable"] == 1


def test_uncertain_and_fake_do_not_pass_clean_cases():
    rule, case, reply = inputs()
    case.expected = "no_violation"
    reply.update(verdict="uncertain", detected=None, quote="")
    report = run_cases([case], [rule], provider=ScriptedJudge(reply))
    assert report["results"][0]["reason"] == "semantic_judgment_uncertain"
    assert report["unavailable"] == 1
    assert run_cases([case], [rule], provider=FakeProvider())["unavailable"] == 1


def test_semantic_compliant_can_fail_expected_violation():
    rule, case, reply = inputs()
    reply.update(verdict="compliant", detected=False, quote="")
    report = run_cases([case], [rule], provider=ScriptedJudge(reply))
    assert report["failed"] == 1
    case.expected = "no_violation"
    assert run_cases([case], [rule], provider=ScriptedJudge(reply))["passed"] == 1


def test_inactive_and_wrong_version_never_reach_provider():
    rule, case, reply = inputs()
    judge = ScriptedJudge(reply)
    rule.status = "deprecated"
    assert run_cases([case], [rule], provider=judge)["unavailable"] == 1
    rule.status = "active"
    case.rule_version = 5
    assert run_cases([case], [rule], provider=judge)["unavailable"] == 1
    assert judge.messages == []


def test_api_uses_selected_provider_and_persists_snapshot(tmp_path, monkeypatch):
    rule, case, reply = inputs()
    root = tmp_path / "synthetic-memory"
    store = MemoryStore(root)
    store.initialize()
    store.save_rule(rule)
    store.save_regression(case)
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai")
    monkeypatch.setattr("paperrule.review.regression.OpenAIAPIProvider",
                        lambda: ScriptedJudge(reply))
    client = TestClient(create_app(root))
    report = client.post("/api/regression/runs", json={}).json()
    assert report["passed"] == 1
    assert store.rule(rule.id) == rule
    assert client.get("/api/regression/runs").json()[0] == report
    exported = client.get("/api/regression/runs/" + report["run_id"] + "/report").json()
    assert exported == report
