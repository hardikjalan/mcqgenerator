"""Validate bearer tokens with Supabase Auth; roles come from the database."""
from dataclasses import dataclass
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from app.db import get_db

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Actor:
    id: str
    role: str
    email: str


def current_actor(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> Actor:
    if not credentials:
        raise HTTPException(401, "Please sign in to continue.")
    try:
        response = get_db().auth.get_user(credentials.credentials)
        user = response.user
    except Exception:
        raise HTTPException(401, "Your session expired. Please sign in again.") from None
    if not user:
        raise HTTPException(401, "Please sign in to continue.")
    result = get_db().table("profiles").select("id,role,email,suspended").eq("id", user.id).maybe_single().execute()
    profile = result.data if result else None
    if not profile or not profile.get("role"):
        raise HTTPException(403, "Complete account setup before continuing.")
    if profile.get("suspended"):
        raise HTTPException(403, "Your account has been suspended. Contact your administrator.")
    return Actor(str(user.id), profile["role"], user.email or "")


def faculty(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role not in ("faculty", "admin"):
        raise HTTPException(403, "Only teachers can manage assessments.")
    return actor


def student(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role != "student":
        raise HTTPException(403, "Only students can take assessments.")
    return actor


def administrator(actor: Actor = Depends(current_actor)) -> Actor:
    if actor.role != "admin":
        raise HTTPException(403, "Administrator access is required.")
    return actor
