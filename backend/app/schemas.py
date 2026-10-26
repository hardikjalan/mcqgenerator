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

from datetime import datetime
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


from app.services.adaptive import Difficulty
from app.services.rag.generation.models import GeneratedQuestion


class GenerateResponse(BaseModel):
    sources: list[SourceResult]
    questions: list[GeneratedQuestion] = []
    # Set once the pool has been stored, so the teacher's browser can link
    # straight to the quiz a student would take.
    quiz_id: str | None = None
    pool_counts: dict[str, int] | None = None


# ── Taking a quiz ─────────────────────────────────────────────────────────────

class QuizSummary(BaseModel):
    """A quiz as it appears in the student's list. Carries no questions."""

    id: str
    subject: str
    topics: str
    grade_level: str
    quiz_length: int
    created_at: datetime


class PublicQuestion(BaseModel):
    """
    A question as the student is allowed to see it.

    Built field by field from GeneratedQuestion rather than by inheriting and
    removing, because a subclass that drops `correct_answer` would silently
    regain it the moment the parent changed. The answer key must never be
    serialisable to the browser, so the safe shape is an explicit allow-list.
    """

    id: int
    question: str
    options: list[str]
    question_type: str
    difficulty: Difficulty
    # Position in the quiz, 1-based, and how many questions there are in total.
    number: int
    total: int


class StartAttemptResponse(BaseModel):
    attempt_id: str
    quiz_id: str
    question: PublicQuestion


class SubmitAnswerRequest(BaseModel):
    selected: str | list[str]


class AnswerFeedback(BaseModel):
    """Shown after an answer is submitted, so the key is no longer a secret."""

    was_correct: bool
    correct_answer: str | list[str]
    difficulty: Difficulty


class SubmitAnswerResponse(BaseModel):
    feedback: AnswerFeedback
    # The next question, or None when the attempt is over.
    question: PublicQuestion | None = None
    finished: bool = False


class AttemptResultBreakdown(BaseModel):
    difficulty: Difficulty
    asked: int
    correct: int


class AttemptResult(BaseModel):
    attempt_id: str
    quiz_id: str
    subject: str
    score: int
    total: int
    # Where the ladder settled. With adaptive difficulty a raw score is
    # misleading on its own - 8/10 at 'hard' is not 8/10 at 'easy' - so the
    # level the student ended on is reported alongside it.
    settled_difficulty: Difficulty
    breakdown: list[AttemptResultBreakdown]

