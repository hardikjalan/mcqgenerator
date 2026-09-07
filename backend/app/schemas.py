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

    Carries counts rather than the extracted text itself. The browser only
    ever displayed the length, so sending the full text meant pushing whole
    documents over the wire to render a number. The text stays server-side,
    which is where question generation needs it anyway.

    ``chunks`` is how many retrieval-sized pieces the text was cut into. A
    file that extracts to plenty of characters but only one chunk is usually
    a sign that something is wrong with it, so it is worth surfacing.
    """

    name: str
    ok: bool
    chars: int
    chunks: int = 0
    sourceId: str | None = None
    indexed: bool = False
    indexNote: str | None = None
    error: str | None = None


class QuestionResponse(BaseModel):
    """One generated multiple-choice question.

    ``evidence`` is the sentence the model quoted from the source material to
    justify the answer, and ``citations`` says where it came from. Both are
    shown to the faculty member: a question they cannot trace back to their
    own material is a question they have no reason to trust.
    """

    question: str
    options: list[str]
    correctIndex: int
    explanation: str = ""
    evidence: list[str] = []


class GenerateResponse(BaseModel):
    """Extraction results, and the quiz if one could be written.

    ``questions`` is empty when generation is not configured or the material
    did not support any — ``note`` says which, so the dashboard can tell the
    difference between "not set up" and "nothing relevant in your files".
    """

    sources: list[SourceResult]
    questions: list[QuestionResponse] = []
    note: str | None = None


class LimitsResponse(BaseModel):
    """Upload rules, served to the frontend by ``GET /limits``.

    ``ocrEnabled`` is included so the upload widget can stop offering image
    formats on a deployment with no OCR provider, rather than accepting a file
    the backend is going to refuse.
    """

    maxFileBytes: int
    maxCumulativeBytes: int
    allowedExtensions: list[str]
    ocrEnabled: bool


class SearchRequest(BaseModel):
    """A question, scoped to the files it may be answered from.

    ``sourceIds`` is required rather than optional. An unscoped search would
    range over every document ever uploaded, by anyone — a data leak dressed
    as a convenience.
    """

    question: str
    sourceIds: list[str]
    topK: int | None = None


class SearchHitResponse(BaseModel):
    """One retrieved chunk.

    ``citation`` is built server-side so every surface that shows a result
    formats the origin the same way.
    """

    content: str
    score: float
    fileName: str
    citation: str
    pageStart: int | None = None
    pageEnd: int | None = None


class SearchResponse(BaseModel):
    hits: list[SearchHitResponse]
