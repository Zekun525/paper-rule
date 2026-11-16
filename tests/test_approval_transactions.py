from concurrent.futures import ThreadPoolExecutor

import pytest

from paperrule.domain.models import RuleRecord
from paperrule.governance.service import ConflictError, Governance
from paperrule.persistence.store import MemoryStore
from paperrule.sync.git import SyncError


def setup_proposal(path):
    store = MemoryStore(path)
    gov = Governance(store)
    proposal = gov.propose(RuleRecord(id="G-transaction", short_title="Synthetic rule",
                                      statement="Explain each implication."))
    return store, gov, proposal


def test_duplicate_concurrent_approval_has_one_event(tmp_path):
    store, gov, proposal = setup_proposal(tmp_path / "memory")
    def approve():
        return gov.approve(proposal.proposal_id, proposal.proposal_hash)[1]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: approve(), range(2)))
    assert sorted(results) == ["already-applied", "applied"]
    assert store.decision_count(proposal.proposal_id) == 1
    assert store.rule("G-transaction").version == 1


def test_failed_commit_restores_authority_records(tmp_path, monkeypatch):
    store, gov, proposal = setup_proposal(tmp_path / "memory")
    head = gov.git.head()
    def fail(*args, **kwargs):
        raise SyncError("Synthetic commit failure")
    monkeypatch.setattr(gov.git, "commit_approved", fail)
    with pytest.raises(SyncError):
        gov.approve(proposal.proposal_id, proposal.proposal_hash)
    assert store.rule("G-transaction") is None
    assert store.decision_count(proposal.proposal_id) == 0
    assert store.proposal(proposal.proposal_id).approved_hash is None
    assert gov.git.head() == head


def test_rejected_proposal_cannot_be_approved(tmp_path):
    store, gov, proposal = setup_proposal(tmp_path / "memory")
    gov.reject(proposal.proposal_id)
    with pytest.raises(ConflictError):
        gov.approve(proposal.proposal_id, proposal.proposal_hash)
    assert store.rule("G-transaction") is None


def test_proposal_identifier_cannot_escape_memory(tmp_path):
    store = MemoryStore(tmp_path / "memory")
    with pytest.raises(ValueError):
        store.proposal("../private")
