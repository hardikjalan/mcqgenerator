"""
schemas.py
==========
The request and response shapes — the contract the Next.js dashboard is
written against.

Request fields are camelCase because that is what the frontend already sends
(frontend/app/dashboard/faculty/page.tsx). Renaming a field on one side without
the other does not raise anything; the dashboard just renders nothing. Change
both together.
"""

from typing import Literal

from pydantic import BaseModel


# ── Request ───────────────────────────────────────────────────────────────────

class QuizConfig(BaseModel):
    subjectName: str
    topicsCovered: str
    learningObjective: str
    gradeLevel: str
    questionType: str
    questionCount: int
    timeLimit: str


class FileItem(BaseModel):
    name: str        # original filename, e.g. "lecture.pdf"
    signedUrl: str   # short-lived Supabase URL to download it from
    size_bytes: int  # browser-reported size, used for the cumulative cap


class GenerateRequest(BaseModel):
    sourceType: Literal["upload", "text"]
    textContent: str | None = None
    files: list[FileItem] | None = None
    config: QuizConfig


# ── Response ──────────────────────────────────────────────────────────────────

class SourceResult(BaseModel):
    """
    One row in the dashboard's "Read from your files" list.

    Carries ``chars`` rather than the extracted text itself. The browser only
    ever displayed the length, so sending the full text meant pushing whole
    documents over the wire to render a number. The text stays server-side,
    which is where question generation needs it anyway.
    """

    name: str
    ok: bool
    chars: int
    error: str | None = None


from app.services.rag.generation.models import GeneratedQuestion


class GenerateResponse(BaseModel):
    sources: list[SourceResult]
    questions: list[GeneratedQuestion] = []

