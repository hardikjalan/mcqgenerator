"""
health.py
=========
Liveness check — used by the frontend to tell "backend is down" apart from
"backend rejected the request", and by the host platform's health probe.
"""

from fastapi import APIRouter

from app.core.responses import success_response

router = APIRouter(tags=["health"])


@router.get("/")
def home():
    return success_response({"status": "Backend is running"})
