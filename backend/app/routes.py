"""
routes.py
=========
The API endpoints.

Routes validate the request and shape the response. When extraction and
generation arrive they go in their own modules and get called from here — a
route that grows a try/except around processing logic has taken on work that
belongs elsewhere.

Errors are raised as HTTPException. The handler in main.py turns every one of
them into ``{"error": "..."}``, so whatever is passed as the detail is shown to
the user verbatim. Keep it a plain sentence, never an internal message.
"""

import logging
from fastapi import APIRouter, HTTPException

from app.schemas import (
    AnswerFeedback,
    AttemptResult,
    AttemptResultBreakdown,
    GenerateRequest,
    GenerateResponse,
    PublicQuestion,
    QuizSummary,
    SourceResult,
    StartAttemptResponse,
    SubmitAnswerRequest,
    SubmitAnswerResponse,
)
from app.services import quiz_session
from app.services.adaptive import DIFFICULTIES
from app.services.rag.generation.models import GeneratedQuestion
from app.services.rag.pipeline import run_assessment_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


def _public(question: GeneratedQuestion, number: int, total: int) -> PublicQuestion:
    """Strip a question down to what the student may see. No correct_answer."""
    return PublicQuestion(
        id=question.id,
        question=question.question,
        options=question.options,
        question_type=question.question_type,
        difficulty=question.difficulty,
        number=number,
        total=total,
    )


@router.get("/")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@router.post("/generate-assessment", response_model=GenerateResponse)
def generate_assessment(payload: GenerateRequest) -> GenerateResponse:
    """Execute the end-to-end RAG pipeline for teacher assessment generation."""
    if payload.sourceType == "text":
        text = (payload.textContent or "").strip()
        if not text:
            raise HTTPException(400, "No text was provided.")
        return GenerateResponse(
            sources=[SourceResult(name="Pasted text", ok=True, chars=len(text))]
        )

    if not payload.files:
        raise HTTPException(400, "No files were provided.")

    try:
        sources, retrieval_result, questions = run_assessment_pipeline(payload)

        # Store the pool straight away. In this prototype there is no publish
        # step: whatever the teacher generates is immediately takeable by a
        # student, which is the behaviour asked for.
        quiz_id = None
        pool_counts = None
        if questions:
            quiz = quiz_session.save_quiz(questions, payload.config)
            quiz_id, pool_counts = quiz.id, quiz.pool_counts()

        return GenerateResponse(
            sources=sources,
            questions=questions,
            quiz_id=quiz_id,
            pool_counts=pool_counts,
        )
    except RuntimeError as exc:
        logger.error("Pipeline service error: %s", exc)
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        logger.error("Pipeline validation error: %s", exc)
        raise HTTPException(422, str(exc))
    except Exception as exc:
        logger.error("Unhandled error in assessment pipeline: %s", exc)
        raise HTTPException(500, f"Assessment pipeline failed: {exc}")



# ── Taking a quiz ─────────────────────────────────────────────────────────────
#
# The pool, and therefore the answer key, never leaves the server. These routes
# hand out one question at a time with `correct_answer` stripped, grade on the
# server, and decide the next difficulty there. See app/services/quiz_session.py.

@router.get("/quizzes", response_model=list[QuizSummary])
def list_quizzes() -> list[QuizSummary]:
    """Every quiz a student can take, newest first."""
    return [
        QuizSummary(
            id=q.id,
            subject=q.subject,
            topics=q.topics,
            grade_level=q.grade_level,
            quiz_length=q.quiz_length,
            created_at=q.created_at,
        )
        for q in quiz_session.list_quizzes()
    ]


@router.post("/quizzes/{quiz_id}/attempts", response_model=StartAttemptResponse)
def start_attempt(quiz_id: str) -> StartAttemptResponse:
    """Begin an attempt and serve the first question."""
    quiz = quiz_session.get_quiz(quiz_id)
    if quiz is None:
        raise HTTPException(404, "That quiz could not be found. It may have expired.")

    try:
        attempt, question = quiz_session.start_attempt(quiz)
    except ValueError as exc:
        raise HTTPException(422, str(exc))

    return StartAttemptResponse(
        attempt_id=attempt.id,
        quiz_id=quiz.id,
        question=_public(question, number=1, total=quiz.quiz_length),
    )


@router.post("/attempts/{attempt_id}/answer", response_model=SubmitAnswerResponse)
def submit_answer(attempt_id: str, payload: SubmitAnswerRequest) -> SubmitAnswerResponse:
    """Grade the current question and serve the next one."""
    attempt = quiz_session.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(404, "That attempt could not be found. It may have expired.")

    quiz = quiz_session.get_quiz(attempt.quiz_id)
    if quiz is None:
        raise HTTPException(404, "The quiz for this attempt is no longer available.")

    try:
        record, nxt = quiz_session.submit_answer(quiz, attempt, payload.selected)
    except ValueError as exc:
        raise HTTPException(409, str(exc))

    return SubmitAnswerResponse(
        feedback=AnswerFeedback(
            was_correct=record.was_correct,
            correct_answer=record.correct_answer,
            difficulty=record.difficulty,
        ),
        question=(
            _public(nxt, number=len(attempt.answers) + 1, total=quiz.quiz_length)
            if nxt else None
        ),
        finished=nxt is None,
    )


@router.get("/attempts/{attempt_id}/result", response_model=AttemptResult)
def attempt_result(attempt_id: str) -> AttemptResult:
    """Final score, plus where the student's difficulty settled."""
    attempt = quiz_session.get_attempt(attempt_id)
    if attempt is None:
        raise HTTPException(404, "That attempt could not be found. It may have expired.")
    if not attempt.is_finished:
        raise HTTPException(409, "This quiz is not finished yet.")

    quiz = quiz_session.get_quiz(attempt.quiz_id)
    subject = quiz.subject if quiz else ""

    breakdown = []
    for d in DIFFICULTIES:
        at_level = [a for a in attempt.answers if a.difficulty == d]
        if at_level:
            breakdown.append(
                AttemptResultBreakdown(
                    difficulty=d,
                    asked=len(at_level),
                    correct=sum(1 for a in at_level if a.was_correct),
                )
            )

    return AttemptResult(
        attempt_id=attempt.id,
        quiz_id=attempt.quiz_id,
        subject=subject,
        score=attempt.score,
        total=len(attempt.answers),
        settled_difficulty=attempt.ladder.difficulty,
        breakdown=breakdown,
    )
