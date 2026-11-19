import json

import pytest

from paperrule.domain.models import RuleRecord
from paperrule.governance.discussion import discuss_with_provider
from paperrule.governance.service import ConflictError, Governance
from paperrule.persistence.store import MemoryStore
from paperrule.providers import AIResponse, OpenAIAPIProvider


def make_proposal(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    gov = Governance(store)
    proposal = gov.propose(RuleRecord(
        id="G-synthetic", short_title="Synthetic rule", statement="Initial wording",
    ))
    return store, gov, proposal


def test_three_ai_revisions_require_explicit_approval(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai")
    store, gov, proposal = make_proposal(tmp_path)
    initial_commit = gov.git.head()
    original_id = proposal.proposal_id
    calls = []

    def chat(self, messages, **kwargs):
        payload = json.loads(messages[-1]["content"])
        calls.append(payload)
        rule = payload["proposal"]["after"]
        rule["statement"] = "Synthetic revision " + str(len(calls))
        return AIResponse(
            text=json.dumps({"reply": "Adjusted the proposal", "rule": rule}),
            provider="openai_api", model="synthetic-test",
        )

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    for message in ["Narrow the wording", "Explain the exception", "I agree"]:
        proposal = discuss_with_provider(gov, original_id, message)
        assert store.rules() == []
        assert gov.git.head() == initial_commit
    assert proposal.revision == 4
    assert len(proposal.chat) == 3
    assert len(calls[-1]["proposal"]["chat"]) == 2
    assert proposal.after.statement == "Synthetic revision 3"
    gov.approve(original_id, proposal.proposal_hash)
    assert store.rule("G-synthetic").statement == "Synthetic revision 3"
    assert store.decisions()[0].proposal_hash == proposal.proposal_hash
    assert gov.git.head() != initial_commit


def test_invalid_ai_reply_retains_draft_and_user_message(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai")
    store, gov, proposal = make_proposal(tmp_path)
    monkeypatch.setattr(
        OpenAIAPIProvider, "chat",
        lambda *args, **kwargs: AIResponse(
            text="Not a validated rule", provider="openai_api", model="synthetic-test",
        ),
    )
    updated = discuss_with_provider(gov, proposal.proposal_id, "Synthetic correction")
    assert updated.after == proposal.after
    assert updated.chat[-1].user_text == "Synthetic correction"
    assert updated.chat[-1].error
    assert store.rules() == []


def test_concurrent_edit_cannot_be_overwritten_by_old_ai_reply(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai")
    store, gov, proposal = make_proposal(tmp_path)

    def chat(self, messages, **kwargs):
        gov.discuss(proposal.proposal_id, "Concurrent local edit")
        return AIResponse(
            text=json.dumps({
                "reply": "Stale response", "rule": proposal.after.model_dump(mode="json"),
            }), provider="openai_api", model="synthetic-test",
        )

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    with pytest.raises(ConflictError, match="changed"):
        discuss_with_provider(gov, proposal.proposal_id, "Older user message")
    saved = store.proposal(proposal.proposal_id)
    assert len(saved.chat) == 1
    assert saved.chat[0].user_text == "Concurrent local edit"



@pytest.mark.parametrize("levels", [
    [], [""], ["synthetic-unknown"], ["paper", "synthetic-unknown"],
], ids=["empty", "blank", "unknown", "partly-unknown"])
def test_ai_scope_levels_require_clarification_without_changing_authority(
    tmp_path, monkeypatch, levels,
):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    store, gov, seed = make_proposal(tmp_path)
    gov.approve(seed.proposal_id, seed.proposal_hash)
    proposal = gov.propose(RuleRecord(
        id="G-synthetic-scope-draft", short_title="Synthetic scope draft",
        statement="Keep the original synthetic draft",
    ))
    baseline_head = gov.git.head()
    baseline_files = {
        path.relative_to(store.root).as_posix(): path.read_bytes()
        for path in (store.root / "rules").rglob("*.json")
    }

    def chat(self, messages, **kwargs):
        assert "scope.levels must contain" in messages[0]["content"]
        rule = proposal.after.model_dump(mode="json")
        rule["statement"] = "Unvalidated synthetic change"
        rule["scope"].update({
            "levels": levels, "paper_ids": ["SYNTHETIC-PAPER"],
            "sections": ["Proof"], "task_types": ["proof_rewrite"],
        })
        return AIResponse(
            text=json.dumps({"reply": "Synthetic scope revision", "rule": rule}),
            provider="openai_api", model="synthetic-test",
        )

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    updated = discuss_with_provider(gov, proposal.proposal_id, "Narrow this synthetic draft")
    assert updated.after == proposal.after
    assert updated.chat[-1].error == "response_schema_invalid"
    assert updated.chat[-1].user_text == "Narrow this synthetic draft"
    assert store.decision_count(proposal.proposal_id) == 0
    assert updated.approved_hash is None
    assert gov.git.head() == baseline_head
    assert {
        path.relative_to(store.root).as_posix(): path.read_bytes()
        for path in (store.root / "rules").rglob("*.json")
    } == baseline_files


def test_ai_explicit_scope_levels_preserve_filters_in_unapproved_draft(tmp_path, monkeypatch):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "openai_api")
    store, gov, proposal = make_proposal(tmp_path)
    baseline_head = gov.git.head()
    scope = {
        "levels": ["paper", "section_task"],
        "paper_ids": ["SYNTHETIC-PAPER"],
        "sections": ["Proof"],
        "task_types": ["proof_rewrite"],
    }

    def chat(self, messages, **kwargs):
        rule = proposal.after.model_dump(mode="json")
        rule["statement"] = "Explain synthetic key reasoning grounds."
        rule["scope"].update(scope)
        return AIResponse(
            text=json.dumps({"reply": "Narrowed the synthetic draft", "rule": rule}),
            provider="openai_api", model="synthetic-test",
        )

    monkeypatch.setattr(OpenAIAPIProvider, "chat", chat)
    updated = discuss_with_provider(gov, proposal.proposal_id, "Narrow the paper and task")
    assert updated.chat[-1].error is None
    assert updated.after.statement == "Explain synthetic key reasoning grounds."
    for name, values in scope.items():
        assert getattr(updated.after.scope, name) == values
    assert updated.after.scope.levels == ["paper", "section_task"]
    assert proposal.after.scope.levels == ["global"]
    assert updated.proposal_hash != proposal.proposal_hash
    assert store.rules() == []
    assert store.decision_count(proposal.proposal_id) == 0
    assert gov.git.head() == baseline_head
