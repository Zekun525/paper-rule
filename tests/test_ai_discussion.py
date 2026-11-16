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
