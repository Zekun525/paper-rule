"""Local owner capabilities and bounded, in-memory browser sessions."""
from __future__ import annotations

import hashlib
import ipaddress
import re
import secrets
import threading
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, StrictStr
from starlette.middleware.base import BaseHTTPMiddleware

from paperrule.domain.models import Record

COOKIE = "paperrule_owner"
SESSION_SECONDS = 8 * 60 * 60
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class LoginInput(Record):
    token: StrictStr = Field(min_length=32, max_length=128)


class LocalOwnerAuth:
    def __init__(self, owner_token: str | None = None):
        self.owner_token = owner_token or secrets.token_urlsafe(32)
        if not re.fullmatch("[A-Za-z0-9_-]{32,128}", self.owner_token):
            raise ValueError("Owner token must be a strong URL-safe capability")
        self._sessions: dict[str, tuple[float, str]] = {}
        self._lock = threading.RLock()
        self._clock = time.monotonic

    def is_owner(self, token: str) -> bool:
        return len(token) == len(self.owner_token) and token.isascii() and secrets.compare_digest(
            token, self.owner_token,
        )

    def new_session(self) -> tuple[str, str]:
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        with self._lock:
            self._expire()
            while len(self._sessions) >= 32:
                self._sessions.pop(next(iter(self._sessions)))
            self._sessions[self._key(token)] = (self._clock() + SESSION_SECONDS, csrf)
        return token, csrf

    @staticmethod
    def _key(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def _expire(self) -> None:
        now = self._clock()
        self._sessions = {key: item for key, item in self._sessions.items() if item[0] > now}

    def session(self, token: str) -> str | None:
        if not token or len(token) > 128:
            return None
        with self._lock:
            self._expire()
            item = self._sessions.get(self._key(token))
            return item[1] if item else None

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(self._key(token), None)


def _origin(value: str) -> tuple[str, str, int]:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"} or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.path or parsed.query or parsed.fragment
    ):
        raise ValueError("Invalid origin")
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    if not 1 <= port <= 65535:
        raise ValueError("Invalid origin port")
    return parsed.scheme, parsed.hostname.lower(), port


def _local_request(request: Request) -> bool:
    if request.client is None:
        return False
    try:
        if not ipaddress.ip_address(request.client.host).is_loopback:
            return False
        hosts = request.headers.getlist("host")
        if len(hosts) != 1:
            return False
        scheme, hostname, port = _origin(request.url.scheme + "://" + hosts[0])
        return scheme in {"http", "https"} and hostname in {
            "127.0.0.1", "localhost", "::1",
        } and 1 <= port <= 65535
    except ValueError:
        return False


def _deny(status: int, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail}, status_code=status, headers={
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })


class LocalOwnerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, owner: LocalOwnerAuth):
        super().__init__(app)
        self.owner = owner

    async def dispatch(self, request: Request, call_next):
        if not _local_request(request):
            return _deny(403, "Only a loopback connection and localhost Host are accepted")
        path = request.url.path
        protected = path == "/api" or path.startswith("/api/") or path in {
            "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect",
        }
        if protected:
            if request.headers.get("sec-fetch-site", "").lower() not in {
                "", "none", "same-origin",
            }:
                return _deny(403, "Cross-origin API access is forbidden")
            if "origin" in request.headers:
                try:
                    if len(request.headers.getlist("origin")) != 1 or _origin(
                        request.headers["origin"]
                    ) != _origin(request.url.scheme + "://" + request.headers["host"]):
                        return _deny(403, "Cross-origin API access is forbidden")
                except ValueError:
                    return _deny(403, "Invalid request origin")
            login = path == "/api/session" and request.method == "POST"
            if not login:
                if len(request.headers.getlist("authorization")) > 1:
                    return _deny(401, "Ambiguous authorization headers")
                authorization = request.headers.get("authorization", "")
                bearer = authorization[7:] if authorization[:7].lower() == "bearer " else ""
                owner = self.owner.is_owner(bearer)
                csrf = self.owner.session(request.cookies.get(COOKIE, ""))
                if (authorization and not owner) or (not owner and csrf is None):
                    return _deny(401, "Open the owner URL printed by paperrule app")
                if not owner and request.method not in SAFE_METHODS:
                    supplied = request.headers.get("x-csrf-token", "")
                    if len(request.headers.getlist("x-csrf-token")) != 1 or not secrets.compare_digest(
                        supplied.encode(), csrf.encode(),
                    ):
                        return _deny(403, "A valid session CSRF token is required")
                request.state.owner_session_csrf = csrf
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
        )
        if protected:
            response.headers["Cache-Control"] = "no-store"
        return response


def register_owner_security(app: FastAPI, owner_token: str | None = None) -> LocalOwnerAuth:
    """Register before the static mount. The capability is never persisted."""
    owner = LocalOwnerAuth(owner_token)
    app.state.owner_auth = owner
    app.add_middleware(LocalOwnerMiddleware, owner=owner)

    def session_response(request: Request) -> JSONResponse:
        csrf = owner.session(request.cookies.get(COOKIE, ""))
        cookie = None
        if csrf is None:
            cookie, csrf = owner.new_session()
        response = JSONResponse({"authenticated": True, "csrf_token": csrf})
        if cookie:
            response.set_cookie(
                COOKIE, cookie, max_age=SESSION_SECONDS, path="/",
                httponly=True, samesite="strict", secure=request.url.scheme == "https",
            )
        return response

    @app.post("/api/session")
    def login(body: LoginInput, request: Request):
        if not owner.is_owner(body.token):
            raise HTTPException(401, "Invalid owner capability")
        return session_response(request)

    @app.get("/api/session")
    def current_session(request: Request):
        return session_response(request)

    @app.delete("/api/session")
    def logout(request: Request):
        owner.revoke(request.cookies.get(COOKIE, ""))
        response = JSONResponse({"authenticated": False})
        response.delete_cookie(COOKIE, path="/")
        return response

    return owner
