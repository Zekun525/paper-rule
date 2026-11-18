import json

import pytest
from owner_client import TestClient

from paperrule.api.app import create_app
from paperrule.domain.models import ReviewReport


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "synthetic-memory")) as value:
        yield value


def test_json_export_preserves_stored_report_and_attachment_headers(client):
    report = ReviewReport(
        review_id="REV-SYNTHETIC-EXPORT",
        task_summary="Synthetic review with unresolved questions.",
        unresolved=["Synthetic evidence still requires human review."],
    ).model_dump(mode="json")
    response = client.post("/api/reviews/import", json=report)
    assert response.status_code == 200
    exported = client.get("/api/reviews/REV-SYNTHETIC-EXPORT/report")
    assert exported.status_code == 200
    assert exported.json() == report
    assert exported.headers["content-type"] == "application/json"
    assert exported.headers["content-disposition"] == (
        'attachment; filename="paperrule-review.json"'
    )
    assert client.get("/api/reviews").json() == [report]
    assert client.get("/api/rules").json() == []


def test_markdown_export_contains_full_data_inside_an_unbreakable_fence(client):
    injection = chr(10).join([
        "Synthetic imported text", chr(96) * 8,
        "# Synthetic misleading heading", chr(96) * 12,
        "合成审查内容",
    ])
    report = ReviewReport(
        review_id="REV-SYNTHETIC-FENCE", task_summary=injection,
        unresolved=["Synthetic question."],
    ).model_dump(mode="json")
    assert client.post("/api/reviews/import", json=report).status_code == 200
    exported = client.get("/api/reviews/REV-SYNTHETIC-FENCE/report?format=markdown")
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/markdown")
    assert exported.headers["content-disposition"] == (
        'attachment; filename="paperrule-review.md"'
    )
    fence = chr(96) * 13
    assert fence + "json" in exported.text
    encoded = exported.text.split(fence + "json" + chr(10), 1)[1].split(
        chr(10) + fence, 1,
    )[0]
    assert json.loads(encoded) == report
    assert "does not approve rules" in exported.text


def test_missing_review_is_a_404_and_does_not_create_data(client):
    response = client.get("/api/reviews/REV-SYNTHETIC-MISSING/report")
    assert response.status_code == 404
    assert client.get("/api/reviews").json() == []


def test_unsupported_export_format_is_rejected(client):
    response = client.get("/api/reviews/REV-SYNTHETIC-MISSING/report?format=html")
    assert response.status_code == 422
    assert client.get("/api/reviews").json() == []
