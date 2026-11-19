import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import PaperProfile, RegressionCase, RuleRecord, RuleScope, digest
from paperrule.governance.service import Governance
from paperrule.persistence.store import MemoryStore
from paperrule.providers.base import AIProvider
from paperrule.review.regression import run_cases, run_stored_cases


class NeverCallProvider(AIProvider):
    name = "synthetic-never-call"

    def __init__(self):
        self.calls = 0

    def chat(self, messages, *, timeout=30):
        self.calls += 1
        raise AssertionError("Unavailable relationship cases must not reach the provider")


def prepare(tmp_path, monkeypatch, semantic=False, state="approved"):
    monkeypatch.setenv("PAPERRULE_PROVIDER", "manual")
    store = MemoryStore(tmp_path / "synthetic-memory")
    store.initialize()
    profiles = [PaperProfile(paper_id="synthetic-a"), PaperProfile(paper_id="synthetic-b")]
    for profile in profiles:
        store.save_paper(profile)
    governance = Governance(store)
    method = "semantic" if semantic else "deterministic"
    parent = RuleRecord(
        id="R-SYNTHETIC-PARENT", short_title="Synthetic parent",
        statement="avoid: synthetic old phrase", check_method=method,
        scope=RuleScope(paper_ids=[profile.paper_id for profile in profiles]),
    )
    initial = governance.propose(parent)
    governance.approve(initial.proposal_id, initial.proposal_hash)
    child = RuleRecord(
        id="R-SYNTHETIC-CHILD", short_title="Synthetic local rule",
        statement="avoid: synthetic new phrase", check_method=method,
        scope=RuleScope(paper_ids=[profiles[0].paper_id]),
        relations=[{"type": "exception_to", "target_id": parent.id, "status": state}],
    )
    proposal = governance.propose(child)
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    cases = [
        RegressionCase(
            id=case_id, rule_id=rule_id, rule_version=1, paper_id=paper_id,
            input_text="synthetic old phrase and synthetic new phrase",
            expected="violation", check_method=method,
        )
        for case_id, rule_id, paper_id in [
            ("RT-SYNTHETIC-PARENT-A", parent.id, profiles[0].paper_id),
            ("RT-SYNTHETIC-CHILD-A", child.id, profiles[0].paper_id),
            ("RT-SYNTHETIC-PARENT-B", parent.id, profiles[1].paper_id),
        ]
    ]
    for case in cases:
        store.save_regression(case)
    return store, governance, profiles, cases


def test_local_regression_marks_replaced_cases_unchecked_and_binds_context(tmp_path, monkeypatch):
    store, governance, profiles, cases = prepare(tmp_path, monkeypatch)
    baseline = store.rules(), store.decisions(), governance.git.head()
    report = run_cases(cases[:2], store.rules(), profiles[0])
    assert report["passed"] == 1
    assert report["failed"] == 0
    assert report["unavailable"] == 1
    assert report["status"] == "incomplete"
    replaced, checked = report["results"]
    assert replaced["reason"] == "rule_replaced_in_context"
    assert replaced["passed"] is None
    assert replaced["findings"] == []
    assert any("R-SYNTHETIC-PARENT" in note and "R-SYNTHETIC-CHILD" in note
               for note in replaced["selection_notes"])
    assert checked["findings"][0]["rule_id"] == "R-SYNTHETIC-CHILD"
    for result in report["results"]:
        assert result["paper_profile_snapshot"] == profiles[0].model_dump(mode="json")
        assert result["paper_profile_sha256"] == digest(profiles[0])
        assert [rule["rule_id"] for rule in result["selection_rules"]] == ["R-SYNTHETIC-CHILD"]
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


def test_other_paper_keeps_the_general_rule_and_rejects_wrong_paper_cases(tmp_path, monkeypatch):
    store, _, profiles, cases = prepare(tmp_path, monkeypatch)
    general = run_cases([cases[2]], store.rules(), profiles[1])
    assert general["passed"] == 1
    assert general["unavailable"] == 0
    assert general["results"][0]["selection_notes"] == []
    wrong = run_cases([cases[1]], store.rules(), profiles[1])
    assert wrong["passed"] == 0
    assert wrong["results"][0]["reason"] == "case_outside_paper"


def test_stored_all_paper_run_resolves_each_case_profile_and_exports_evidence(tmp_path, monkeypatch):
    store, governance, _, _ = prepare(tmp_path, monkeypatch)
    baseline = store.rules(), store.decisions(), governance.git.head()
    report = run_stored_cases(store)
    assert report["passed"] == 2
    assert report["unavailable"] == 1
    assert {row["paper_profile_snapshot"]["paper_id"] for row in report["results"]} == {
        "synthetic-a", "synthetic-b",
    }
    with TestClient(create_app(store.root)) as client:
        url = "/api/regression/runs/" + report["run_id"] + "/report"
        assert client.get(url).json() == report
        markdown = client.get(url + "?format=markdown")
        assert markdown.status_code == 200
        assert "rule_replaced_in_context" in markdown.text
        assert "selection_rules" in markdown.text
        assert client.get("/api/regression/runs").json()[0] == report
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


def test_missing_case_profile_does_not_reach_a_provider(tmp_path, monkeypatch):
    store, _, _, cases = prepare(tmp_path, monkeypatch, semantic=True)
    provider = NeverCallProvider()
    report = run_cases([cases[1]], store.rules(), provider=provider)
    assert provider.calls == 0
    assert report["unavailable"] == 1
    assert report["results"][0]["reason"] == "scope_profile_unavailable"
    assert report["results"][0]["paper_profile_snapshot"] is None


@pytest.mark.parametrize("semantic", [False, True])
def test_stale_relationship_blocks_regression_before_evaluation(tmp_path, monkeypatch, semantic):
    store, governance, profiles, cases = prepare(tmp_path, monkeypatch, semantic=semantic)
    parent = store.rule("R-SYNTHETIC-PARENT").model_copy(deep=True)
    parent.statement = "avoid: revised synthetic phrase"
    proposal = governance.propose(parent, "amend")
    governance.approve(proposal.proposal_id, proposal.proposal_hash)
    baseline = store.rules(), store.decisions(), governance.git.head()
    provider = NeverCallProvider()
    report = run_cases([cases[1]], store.rules(), profiles[0], provider=provider)
    assert provider.calls == 0
    assert report["passed"] == report["failed"] == 0
    assert report["unavailable"] == 1
    assert report["results"][0]["reason"] == "rule_relation_unresolved"
    assert report["results"][0]["findings"] == []
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline


def test_candidate_relationship_does_not_suppress_regression_cases(tmp_path, monkeypatch):
    store, _, profiles, cases = prepare(tmp_path, monkeypatch, state="candidate")
    report = run_cases(cases[:2], store.rules(), profiles[0])
    assert report["passed"] == 2
    assert report["unavailable"] == 0
    assert all(result["selection_notes"] == [] for result in report["results"])
