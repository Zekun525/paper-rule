"""Explicitly authenticated transport for existing owner API integration tests."""
from fastapi.testclient import TestClient as RawTestClient


class TestClient(RawTestClient):
    __test__ = False

    def __init__(self, app, **kwargs):
        headers = dict(kwargs.pop("headers", None) or {})
        headers.setdefault("Authorization", "Bearer " + app.state.owner_auth.owner_token)
        kwargs.setdefault("base_url", "http://127.0.0.1")
        kwargs.setdefault("client", ("127.0.0.1", 50000))
        super().__init__(app, headers=headers, **kwargs)
