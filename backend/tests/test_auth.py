"""
test_auth.py
============
Who the API thinks is calling.

Tokens are verified against a stand-in Supabase rather than mocked out, so the
header names and the status-code handling are actually exercised — those are
what break against the real service.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request

from app import auth, config

STATE: dict = {"status": 200, "body": {"id": "teacher-a", "email": "a@school.edu"}, "calls": []}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        STATE["calls"].append(dict(self.headers))
        body = json.dumps(STATE["body"]).encode()
        self.send_response(STATE["status"])
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def supabase():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


@pytest.fixture
def configured(monkeypatch, supabase):
    monkeypatch.setattr(config, "SUPABASE_URL", supabase)
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", "service-key")
    auth._cache.clear()
    STATE["status"] = 200
    STATE["body"] = {"id": "teacher-a", "email": "a@school.edu"}
    STATE["calls"].clear()


def _request(token: str | None = None) -> Request:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return Request({
        "type": "http", "method": "POST", "path": "/x",
        "headers": Headers(headers).raw, "query_string": b"",
    })


# ── Local development ─────────────────────────────────────────────────────────

def test_no_supabase_means_no_authentication(monkeypatch):
    """A deployment with no Supabase project is a development one — there is
    nothing there to protect, and demanding a token would make it unusable."""
    monkeypatch.setattr(config, "SUPABASE_URL", "")

    assert auth.current_user(_request()) is None
    assert auth.owner_id(None) is None


# ── Required once Supabase exists ─────────────────────────────────────────────

def test_a_missing_token_is_refused(configured):
    """The moment there are real users, anonymous uploads are how one
    teacher's material ends up in another teacher's quiz."""
    with pytest.raises(HTTPException) as excinfo:
        auth.current_user(_request())

    assert excinfo.value.status_code == 401


def test_a_malformed_header_is_refused(configured):
    request = Request({
        "type": "http", "method": "POST", "path": "/x",
        "headers": Headers({"Authorization": "Basic abc123"}).raw, "query_string": b"",
    })

    with pytest.raises(HTTPException) as excinfo:
        auth.current_user(request)

    assert excinfo.value.status_code == 401


def test_a_valid_token_identifies_the_caller(configured):
    user = auth.current_user(_request("good-token"))

    assert user.id == "teacher-a"
    assert user.email == "a@school.edu"


def test_the_token_and_api_key_are_both_sent(configured):
    """Supabase needs the project key as apikey and the user's token as the
    bearer; sending only one returns someone else's answer or none at all."""
    auth.current_user(_request("good-token"))

    (headers,) = STATE["calls"]
    assert headers["apikey"] == "service-key"
    assert headers["Authorization"] == "Bearer good-token"


def test_an_expired_token_is_refused(configured):
    STATE["status"] = 401

    with pytest.raises(HTTPException) as excinfo:
        auth.current_user(_request("stale-token"))

    assert excinfo.value.status_code == 401
    assert "sign in" in excinfo.value.detail.lower()


def test_verification_is_cached(configured):
    """One round trip per request would put an HTTP call in front of every
    upload, for an answer that changes rarely."""
    auth.current_user(_request("good-token"))
    auth.current_user(_request("good-token"))

    assert len(STATE["calls"]) == 1


def test_different_tokens_are_not_confused(configured):
    auth.current_user(_request("token-a"))
    STATE["body"] = {"id": "teacher-b"}
    second = auth.current_user(_request("token-b"))

    assert second.id == "teacher-b"
    assert len(STATE["calls"]) == 2


# ── When the check itself breaks ──────────────────────────────────────────────

def test_an_unreachable_supabase_is_not_a_sign_in_problem(monkeypatch):
    """503, not 401. Telling a signed-in teacher to sign in again sends them
    round a loop that cannot fix anything."""
    monkeypatch.setattr(config, "SUPABASE_URL", "http://127.0.0.1:1")
    monkeypatch.setattr(config, "SUPABASE_SERVICE_KEY", "k")
    auth._cache.clear()

    with pytest.raises(HTTPException) as excinfo:
        auth.current_user(_request("token"))

    assert excinfo.value.status_code == 503


def test_a_response_without_a_user_id_is_refused(configured):
    STATE["body"] = {"error": "something odd"}

    with pytest.raises(HTTPException) as excinfo:
        auth.current_user(_request("token"))

    assert excinfo.value.status_code == 401
