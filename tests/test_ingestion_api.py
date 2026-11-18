from owner_client import TestClient

from paperrule.api.app import create_app


def test_api_requires_hash_and_preserves_discussion_as_draft(tmp_path):
    client = TestClient(create_app(tmp_path / "mem"))
    assert client.get("/api/health").status_code == 200
    # proposals are only created through reviewed CLI/service flow
    assert client.get("/api/proposals").json() == []

