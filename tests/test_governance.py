from pathlib import Path

import pytest

from paperrule.domain.models import PaperProfile, RuleRecord, RuleScope
from paperrule.governance.service import ConflictError, Governance
from paperrule.persistence.store import MemoryStore
from paperrule.retrieval.context import build_context


def test_chat_does_not_activate_until_explicit_approval(tmp_path: Path):
    store = MemoryStore(tmp_path / "private")
    gov = Governance(store)
    proposal = gov.propose(RuleRecord(id="G-1", short_title="Clear proofs", statement="Show each implication"))
    for text in ("Could this be narrower?", "Keep equations unchanged", "Apply to proofs only"):
        proposal = gov.discuss(proposal.proposal_id, text)
    assert store.rule("G-1") is None
    assert store.decision_count(proposal.proposal_id) == 0
    applied, result = gov.approve(proposal.proposal_id, proposal.proposal_hash)
    assert result == "applied"
    assert store.rule(applied.after.id).status.value == "active"
    assert store.decision_count(proposal.proposal_id) == 1


def test_stale_hash_and_stale_base_are_rejected(tmp_path: Path):
    store = MemoryStore(tmp_path / "private")
    gov = Governance(store)
    p = gov.propose(RuleRecord(id="G-2", short_title="One", statement="A"))
    with pytest.raises(ConflictError):
        gov.approve(p.proposal_id, "wrong")
    gov.approve(p.proposal_id, p.proposal_hash)
    p2 = gov.propose(RuleRecord(id="G-2", short_title="Two", statement="B"), operation="amend")
    changed = store.rule("G-2").model_copy(update={"version": 2})
    store.save_rule(changed)
    with pytest.raises(ConflictError):
        gov.approve(p2.proposal_id, p2.proposal_hash)


def test_context_filters_by_paper_and_section(tmp_path: Path):
    store = MemoryStore(tmp_path / "private")
    store.save_rule(RuleRecord(id="G", status="active", short_title="Global", statement="general"))
    store.save_rule(RuleRecord(id="P", status="active", short_title="Paper", statement="specific",
                               scope=RuleScope(levels=["paper"], paper_ids=["p1"], sections=["intro"])))
    result = build_context(store.rules(), PaperProfile(paper_id="p1"), "intro", "revise")
    assert [entry["rule"]["id"] for entry in result["rules"]] == ["G", "P"]

