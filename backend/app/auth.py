"""
auth.py
=======
Who is calling.

Until now the API had no idea. That was survivable with one teacher and
becomes a data leak with two: uploads, chunks and searches were all scoped by
ids supplied in the request body, which is a claim rather than a fact.

Tokens are verified by asking Supabase, not by decoding them here. Local
verification needs the project's JWT secret — another secret to distribute and
rotate — and it cannot know that a user was deleted or signed out thirty
seconds ago. The cost is one HTTP round trip, which a short cache keeps off
the hot path.

Authentication is required whenever Supabase is configured. A deployment with
no Supabase project is a local development one, and there is nothing there to
protect; a deployment with one has real users, and an endpoint that accepts
anonymous uploads alongside them is how one teacher ends up reading another's
material.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request

from app import config

_TIMEOUT = httpx.Timeout(connect=5.0, read=10.0, write=5.0, pool=5.0)

# token → (user, expires_at). Bounded so a stream of junk tokens cannot grow
# it without limit.
_cache: dict[str, tuple["AuthenticatedUser", float]] = {}
_CACHE_MAX = 512


@dataclass(frozen=True)
class AuthenticatedUser:
    id: str
    email: str | None = None


def current_user(request: Request) -> AuthenticatedUser | None:
    """FastAPI dependency: the verified caller, or None in local development.

    Raises 401 when Supabase is configured and the token is missing, malformed
    or rejected.
    """
    if not config.auth_required():
        return None

    token = _bearer_token(request)
    if not token:
        raise HTTPException(401, "Please sign in again.")

    cached = _cache.get(token)
    if cached and cached[1] > time.monotonic():
        return cached[0]

    user = _verify(token)
    _remember(token, user)
    return user


def owner_id(user: AuthenticatedUser | None) -> str | None:
    """The id to record on stored rows. None in local development."""
    return user.id if user else None


# ── Internal ──────────────────────────────────────────────────────────────────

def _bearer_token(request: Request) -> str | None:
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


def _verify(token: str) -> AuthenticatedUser:
    """Ask Supabase who this token belongs to."""
    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.get(
                f"{config.SUPABASE_URL}/auth/v1/user",
                headers={
                    "apikey": config.SUPABASE_SERVICE_KEY,
                    "Authorization": f"Bearer {token}",
                },
            )
    except httpx.HTTPError as exc:
        # Sign-in is not broken, the check is — so this is a 503, not a 401.
        # Telling a signed-in teacher to sign in again would send them round a
        # loop that cannot fix anything.
        print(f"[auth] could not reach Supabase: {type(exc).__name__}: {exc}")
        raise HTTPException(503, "Could not verify your session. Please try again.") from exc

    if response.status_code == 401 or response.status_code == 403:
        raise HTTPException(401, "Your session has expired. Please sign in again.")

    if response.status_code >= 400:
        print(f"[auth] unexpected {response.status_code}: {response.text[:200]}")
        raise HTTPException(503, "Could not verify your session. Please try again.")

    body = response.json() or {}
    user_id = body.get("id")
    if not user_id:
        raise HTTPException(401, "Your session has expired. Please sign in again.")

    return AuthenticatedUser(id=str(user_id), email=body.get("email"))


def _remember(token: str, user: AuthenticatedUser) -> None:
    if len(_cache) >= _CACHE_MAX:
        _cache.clear()
    _cache[token] = (user, time.monotonic() + config.AUTH_CACHE_SECONDS)
