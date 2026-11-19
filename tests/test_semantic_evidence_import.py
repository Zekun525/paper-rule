"""Imported model records must retain consistent bindings; external text is not certified."""
from copy import deepcopy

import pytest
from owner_client import TestClient
from test_semantic_review_integration import SyntheticProvider, document
from test_semantic_review_integration import memory as synthetic_memory

from paperrule.api.app import create_app
from paperrule.domain.models import ReviewReport
from paperrule.review.files import check_documents
from paperrule.review.importing import import_report

memory = synthetic_memory


def generated_report(memory, *, mode="violation"):
    store, _governance, profile = memory
    provider = SyntheticProvider(mode)
    report = check_documents(store, [document()], profile,
                             semantic=True, semantic_provider=provider)
    report["review_id"] = "REV-SYNTHETIC-IMPORTED-EVIDENCE"
    return report, provider


def test_generated_semantic_evidence_can_be_imported_and_exported_without_approval(memory):
    store, governance, _profile = memory
    payload, provider = generated_report(memory)
    baseline = store.rules(), store.decisions(), governance.git.head()
    report = ReviewReport.model_validate(payload)
    assert import_report(store, report) == report
    assert import_report(store, report) == report
    assert len(provider.calls) == 1
    assert (store.rules(), store.decisions(), governance.git.head()) == baseline
    with TestClient(create_app(store.root)) as client:
        response = client.get("/api/reviews/" + report.review_id + "/report")
        assert response.status_code == 200
        assert response.json() == payload


@pytest.mark.parametrize("corruption", [
    "unknown-rule", "stale-version", "rule-hash", "file-hash", "missing-file",
    "duplicate-file", "missing-snapshot", "missing-snapshot-hash",
    "wrong-selection-mode", "duplicate-lines", "boolean-line", "checked-count",
    "missing-model", "fake-provider", "missing-judgment", "judgment-rule",
    "judgment-version", "contradictory-verdict", "missing-judgment-finding",
    "missing-report-finding", "wrong-finding-rule", "wrong-quote",
    "wrong-location", "wrong-recommendation", "duplicate-evidence",
], ids=lambda value: value)
def test_inconsistent_semantic_evidence_is_rejected_without_persistence(memory, corruption):
    store, governance, _profile = memory
    payload, _provider = generated_report(memory)
    baseline = store.reviews(), store.rules(), store.decisions(), governance.git.head()
    item = payload["semantic_evidence"][0]
    if corruption == "unknown-rule":
        item["rule_id"] = "R-SYNTHETIC-MISSING"
    elif corruption == "stale-version":
        item["rule_version"] += 1
    elif corruption == "rule-hash":
        item["rule_sha256"] = "0" * 64
    elif corruption == "file-hash":
        item["file_sha256"] = "0" * 64
    elif corruption == "missing-file":
        payload["files"] = []
    elif corruption == "duplicate-file":
        payload["files"].append(deepcopy(payload["files"][0]))
    elif corruption == "missing-snapshot":
        payload["rule_snapshot"] = []
        payload["rule_snapshot_sha256"] = None
    elif corruption == "missing-snapshot-hash":
        payload["rule_snapshot_sha256"] = None
    elif corruption == "wrong-selection-mode":
        item["selection"]["mode"] = "changed_lines"
    elif corruption == "duplicate-lines":
        item["selection"]["line_numbers"] = [1, 1]
        item["checked_line_count"] = 2
    elif corruption == "boolean-line":
        item["selection"]["line_numbers"] = [True]
    elif corruption == "checked-count":
        item["checked_line_count"] += 1
    elif corruption == "missing-model":
        item["model"] = ""
    elif corruption == "fake-provider":
        item["provider"] = "fake"
    elif corruption == "missing-judgment":
        item["judgment"] = {}
    elif corruption == "judgment-rule":
        item["judgment"]["rule_id"] = "R-SYNTHETIC-OTHER"
    elif corruption == "judgment-version":
        item["judgment"]["rule_version"] += 1
    elif corruption == "contradictory-verdict":
        item["judgment"]["verdict"] = "compliant"
    elif corruption == "missing-judgment-finding":
        item["judgment"]["findings"] = []
    elif corruption == "missing-report-finding":
        payload["findings"] = [
            finding for finding in payload["findings"]
            if finding["rule_id"] != item["rule_id"]
        ]
    elif corruption == "wrong-finding-rule":
        item["findings"][0]["rule_id"] = "R-SYNTHETIC-OTHER"
    elif corruption == "wrong-quote":
        item["findings"][0]["quote"] = "Synthetic invented quote."
        payload["findings"][-1]["quote"] = "Synthetic invented quote."
    elif corruption == "wrong-location":
        item["findings"][0]["location"] = "synthetic.tex:9"
        payload["findings"][-1]["location"] = "synthetic.tex:9"
    elif corruption == "wrong-recommendation":
        item["findings"][0]["recommendation"] = "Synthetic changed recommendation."
        payload["findings"][-1]["recommendation"] = "Synthetic changed recommendation."
    elif corruption == "duplicate-evidence":
        payload["semantic_evidence"].append(deepcopy(item))
    else:
        raise AssertionError("Unknown synthetic corruption")
    with pytest.raises(ValueError):
        import_report(store, ReviewReport.model_validate(payload))
    assert (store.reviews(), store.rules(), store.decisions(), governance.git.head()) == baseline


@pytest.mark.parametrize("mode", ["compliant", "uncertain", "unavailable"])
def test_valid_nonviolation_and_unavailable_evidence_keep_original_status(memory, mode):
    store, _governance, _profile = memory
    payload, _provider = generated_report(memory, mode=mode)
    original = ReviewReport.model_validate(payload)
    assert import_report(store, original) == original
    assert original.semantic_evidence[0].human_review == "pending"
    if mode != "compliant":
        assert original.semantic_status == "not_reviewed"
        assert original.semantic_evidence[0].checked_line_count == 0


def test_api_rejects_inconsistent_file_evidence(memory):
    store, _governance, _profile = memory
    payload, _provider = generated_report(memory)
    baseline = store.reviews()
    payload["semantic_evidence"][0]["file_sha256"] = "0" * 64
    with TestClient(create_app(store.root)) as client:
        response = client.post("/api/reviews/import", json=payload)
    assert response.status_code == 400
    assert store.reviews() == baseline
