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

from pydantic import BaseModel, Field, ConfigDict, field_validator


# ── Request ───────────────────────────────────────────────────────────────────

class QuizConfig(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    subjectName: str = Field(min_length=1, max_length=200)
    topicsCovered: str = Field(min_length=1, max_length=2000)
    learningObjective: str = Field(min_length=1, max_length=2000)
    gradeLevel: str = Field(min_length=1, max_length=200)
    questionType: Literal["single", "multiple", "truefalse", "all"]
    questionCount: int = Field(ge=1, le=30)
    timeLimit: str = Field(default="", pattern=r"^\d{0,4}$")
    bloomLevels: list[Literal["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"]] = Field(
        default_factory=lambda: ["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"],
        min_length=1, max_length=6,
    )
    adaptive: bool = True

    @field_validator("timeLimit")
    @classmethod
    def valid_time_limit(cls, value: str) -> str:
        if value and not 1 <= int(value) <= 1440:
            raise ValueError("Time limit must be between 1 and 1,440 minutes.")
        return value


class FileItem(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    signedUrl: str = Field(min_length=1, max_length=4096)
    size_bytes: int = Field(ge=1, le=5 * 1024 * 1024)


class GenerateRequest(BaseModel):
    sourceType: Literal["upload", "text"]
    textContent: str | None = Field(default=None, max_length=100000)
    files: list[FileItem] | None = Field(default=None, max_length=10)
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
    questions: list[GeneratedQuestion] = Field(default_factory=list)
    assessmentId: str | None = None

