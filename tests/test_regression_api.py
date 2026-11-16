from fastapi.testclient import TestClient

from paperrule.api.app import create_app


def test_regression_api_persists_and_exports_unavailable_results(tmp_path):
    client = TestClient(create_app(tmp_path / "synthetic-memory"))
    case = {
        "id": "RT-synthetic", "rule_id": "G-missing",
        "input_text": "Synthetic evidence", "expected": "no_violation",
    }
    assert client.post("/api/regression/cases", json=case).status_code == 200
    assert client.get("/api/regression/cases").json()[0]["id"] == case["id"]
    response = client.post("/api/regression/runs", json={})
    assert response.status_code == 200
    recorded = response.json()
    assert recorded["status"] == "incomplete"
    assert recorded["passed"] == 0
    assert recorded["unavailable"] == 1
    assert recorded["results"][0]["reason"] == "rule_not_found"
    assert client.get("/api/regression/runs").json()[0] == recorded
    url = "/api/regression/runs/" + recorded["run_id"] + "/report"
    exported = client.get(url)
    assert exported.status_code == 200
    assert exported.json() == recorded
    assert "attachment" in exported.headers["content-disposition"]
    markdown = client.get(url, params={"format": "markdown"})
    assert markdown.status_code == 200
    assert "Unavailable: 1" in markdown.text
    assert "rule_not_found" in markdown.text
    assert client.get(url, params={"format": "html"}).status_code == 422
    assert client.get("/api/regression/runs/RUN-missing/report").status_code == 404


def test_regression_run_for_unknown_paper_is_rejected(tmp_path):
    client = TestClient(create_app(tmp_path / "synthetic-memory"))
    response = client.post("/api/regression/runs", json={"paper_id": "unknown"})
    assert response.status_code == 400
    assert client.get("/api/regression/runs").json() == []
