import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from paperrule.api.security import COOKIE, SESSION_SECONDS, register_owner_security

TOKEN = "synthetic-owner-capability-" + "x" * 32


@pytest.fixture
def secured():
    app = FastAPI()
    owner = register_owner_security(app, TOKEN)
    changes = []

    @app.get("/")
    def home():
        return {"public": "synthetic workbench"}

    @app.get("/api/rules")
    def rules():
        return changes

    @app.post("/api/approve")
    def approve():
        changes.append("synthetic approved change")
        return {"approved": True}

    client = TestClient(app, base_url="http://127.0.0.1",
                        client=("127.0.0.1", 50000))
    return app, owner, changes, client


def login(client):
    response = client.post("/api/session", json={"token": TOKEN})
    assert response.status_code == 200
    return response.json()["csrf_token"]


def test_private_api_and_schema_require_owner(secured):
    _, _, changes, client = secured
    assert client.get("/").status_code == 200
    for path in ("/api/rules", "/api/session", "/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 401
    assert client.post("/api/approve", json={}).status_code == 401
    assert changes == []


def test_session_requires_csrf_for_changes_and_supports_logout(secured):
    _, _, changes, client = secured
    csrf = login(client)
    assert client.get("/api/rules").json() == []
    assert client.post("/api/approve", json={}).status_code == 403
    assert client.post("/api/approve", headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert changes == []
    assert client.post("/api/approve", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert changes == ["synthetic approved change"]
    assert client.delete("/api/session", headers={"X-CSRF-Token": csrf}).status_code == 200
    assert client.get("/api/rules").status_code == 401


def test_bearer_is_supported_without_disabling_origin_checks(secured):
    _, _, changes, client = secured
    headers = {"Authorization": "Bearer " + TOKEN}
    assert client.get("/api/rules", headers=headers).status_code == 200
    assert client.post("/api/approve", headers={
        **headers, "Origin": "https://synthetic-attacker.invalid",
    }).status_code == 403
    assert changes == []
    assert client.post("/api/approve", headers=headers).status_code == 200


@pytest.mark.parametrize("origin", [
    "null", "https://synthetic-attacker.invalid", "http://localhost",
    "http://127.0.0.1:8765", "http://127.0.0.1/path", "http://user@127.0.0.1",
])
def test_foreign_or_malformed_origins_cannot_login_or_change(secured, origin):
    _, _, changes, client = secured
    assert client.post("/api/session", json={"token": TOKEN},
                       headers={"Origin": origin}).status_code == 403
    csrf = login(client)
    assert client.post("/api/approve", headers={
        "Origin": origin, "X-CSRF-Token": csrf,
    }).status_code == 403
    assert changes == []


@pytest.mark.parametrize("host", [
    "synthetic-attacker.invalid", "127.0.0.1.synthetic-attacker.invalid",
    "user@localhost", "localhost:not-a-port", "localhost/path",
])
def test_untrusted_host_is_rejected_even_with_owner_token(secured, host):
    _, _, changes, client = secured
    response = client.post("/api/approve", headers={
        "Host": host, "Authorization": "Bearer " + TOKEN,
    })
    assert response.status_code == 403
    assert changes == []


def test_remote_connection_cannot_spoof_loopback_with_forwarded_header(secured):
    app, _, changes, _ = secured
    remote = TestClient(app, base_url="http://127.0.0.1",
                        client=("203.0.113.9", 50000))
    response = remote.post("/api/approve", headers={
        "Authorization": "Bearer " + TOKEN, "X-Forwarded-For": "127.0.0.1",
    })
    assert response.status_code == 403
    assert changes == []


def test_session_tokens_expire_and_are_bounded(secured):
    _, owner, _, client = secured
    login(client)
    now = owner._clock()
    owner._clock = lambda: now + SESSION_SECONDS + 1
    assert client.get("/api/rules").status_code == 401
    for _ in range(40):
        owner.new_session()
    assert len(owner._sessions) == 32


def test_cookie_flags_and_private_response_headers(secured):
    _, _, _, client = secured
    response = client.post("/api/session", json={"token": TOKEN})
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    assert response.headers["cache-control"] == "no-store"
    assert TOKEN not in response.text and TOKEN not in cookie
    assert client.cookies.get(COOKIE)
    response = client.get("/api/rules")
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"


def test_bad_capability_and_cross_site_fetch_are_rejected(secured):
    _, _, changes, client = secured
    assert client.post("/api/session", json={"token": "wrong-" + "x" * 40}).status_code == 401
    assert client.post("/api/session", json={"token": TOKEN},
                       headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/api/session", json={
        "token": TOKEN, "unexpected_approval": True,
    }).status_code == 422
    assert changes == []


def test_matching_origin_and_fetch_metadata_allow_legitimate_session(secured):
    _, _, changes, client = secured
    csrf = login(client)
    response = client.post("/api/approve", headers={
        "Origin": "http://127.0.0.1", "Sec-Fetch-Site": "same-origin",
        "X-CSRF-Token": csrf,
    })
    assert response.status_code == 200
    assert len(changes) == 1


def test_invalid_authorization_does_not_fall_back_to_cookie(secured):
    _, _, changes, client = secured
    csrf = login(client)
    assert client.post("/api/approve", headers={
        "Authorization": "Bearer invalid", "X-CSRF-Token": csrf,
    }).status_code == 401
    assert changes == []
