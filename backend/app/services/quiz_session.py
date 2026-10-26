"""
quiz_session.py
===============
The adaptive quiz engine, plus the prototype store that holds quizzes between
the teacher generating one and a student taking it.

PROTOTYPE STORAGE
-----------------
Quizzes and attempts live in module-level dicts. That means they are lost on
restart, are not shared between worker processes, and grow without bound. This
is deliberate for now - it makes a generated quiz visible to a student
immediately with no schema, no migration and no RLS policy to get wrong. Every
read and write goes through this module, so replacing it with Supabase later is
a change to this file and nothing else.

WHY THE ENGINE IS SERVER-SIDE
-----------------------------
The question pool contains the correct answers. If the client received the pool
it would receive the answer key with it, and a student could read it straight
out of devtools. So the API hands out ONE question at a time with the answer
stripped, grades on the server, and decides the next difficulty here. The
browser never holds anything it should not.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Union

from pydantic import BaseModel, Field

from app.schemas import QuizConfig
from app.services.adaptive import DIFFICULTIES, Difficulty, LadderState
from app.services.rag.generation.models import GeneratedQuestion

logger = logging.getLogger(__name__)


# ── Stored shapes ─────────────────────────────────────────────────────────────

class StoredQuiz(BaseModel):
    """A generated quiz waiting to be taken."""

    id: str
    subject: str
    topics: str
    grade_level: str
    quiz_length: int
    pool: list[GeneratedQuestion]
    created_at: datetime

    def pool_counts(self) -> dict[str, int]:
        return {d: sum(1 for q in self.pool if q.difficulty == d) for d in DIFFICULTIES}


class AnswerRecord(BaseModel):
    """One answered question within an attempt."""

    question_id: int
    question: str
    difficulty: Difficulty
    bloom_level: str
    selected: Union[str, list[str]]
    correct_answer: Union[str, list[str]]
    was_correct: bool


class Attempt(BaseModel):
    """A student's run through one quiz."""

    id: str
    quiz_id: str
    ladder: LadderState = Field(default_factory=LadderState)
    asked_ids: list[int] = Field(default_factory=list)
    answers: list[AnswerRecord] = Field(default_factory=list)
    # The question the student is currently looking at, if any.
    current_id: int | None = None
    started_at: datetime
    finished_at: datetime | None = None

    @property
    def is_finished(self) -> bool:
        return self.finished_at is not None

    @property
    def score(self) -> int:
        return sum(1 for a in self.answers if a.was_correct)


# ── Store ─────────────────────────────────────────────────────────────────────

_QUIZZES: dict[str, StoredQuiz] = {}
_ATTEMPTS: dict[str, Attempt] = {}


def save_quiz(
    pool: list[GeneratedQuestion],
    config: QuizConfig,
) -> StoredQuiz:
    """Store a freshly generated pool and return it with its new id."""
    quiz = StoredQuiz(
        id=uuid.uuid4().hex[:12],
        subject=config.subjectName,
        topics=config.topicsCovered,
        grade_level=config.gradeLevel,
        quiz_length=config.questionCount,
        pool=pool,
        created_at=datetime.now(timezone.utc),
    )
    _QUIZZES[quiz.id] = quiz
    logger.info(
        "Quiz %s stored: %s, %d questions in pool for a %d-question quiz %s",
        quiz.id, quiz.subject, len(pool), quiz.quiz_length, quiz.pool_counts(),
    )
    return quiz


def list_quizzes() -> list[StoredQuiz]:
    """Newest first, so a student sees what their teacher just made."""
    return sorted(_QUIZZES.values(), key=lambda q: q.created_at, reverse=True)


def get_quiz(quiz_id: str) -> StoredQuiz | None:
    return _QUIZZES.get(quiz_id)


def get_attempt(attempt_id: str) -> Attempt | None:
    return _ATTEMPTS.get(attempt_id)


# ── Engine ────────────────────────────────────────────────────────────────────

def _is_correct(selected: Union[str, list[str]], correct: Union[str, list[str]]) -> bool:
    """Compare an answer to the key, order- and case-insensitively.

    Multi-select must match as a SET: picking three of three correct options is
    right, picking two of them is not.
    """
    norm = lambda v: {s.strip().lower() for s in ([v] if isinstance(v, str) else v)}
    return norm(selected) == norm(correct)


def _pick_question(quiz: StoredQuiz, attempt: Attempt) -> GeneratedQuestion | None:
    """Choose the next unseen question at (or nearest to) the current level.

    The pool is sized so the exact difficulty is always available - see
    adaptive.plan_pool. The widening fallback exists because the pool is written
    by a language model that can return the wrong mix: if its bucket is short,
    the quiz steps to the nearest difficulty rather than failing mid-attempt.
    """
    seen = set(attempt.asked_ids)
    target = DIFFICULTIES.index(attempt.ladder.difficulty)

    for distance in range(len(DIFFICULTIES)):
        for idx in (target - distance, target + distance):
            if not 0 <= idx < len(DIFFICULTIES):
                continue
            wanted = DIFFICULTIES[idx]
            for q in quiz.pool:
                if q.id not in seen and q.difficulty == wanted:
                    if distance:
                        logger.warning(
                            "Attempt %s: no unseen '%s' questions left, substituting '%s'",
                            attempt.id, attempt.ladder.difficulty, wanted,
                        )
                    return q
    return None


def start_attempt(quiz: StoredQuiz) -> tuple[Attempt, GeneratedQuestion]:
    """Begin an attempt and serve its first question."""
    attempt = Attempt(
        id=uuid.uuid4().hex[:12],
        quiz_id=quiz.id,
        started_at=datetime.now(timezone.utc),
    )
    question = _pick_question(quiz, attempt)
    if question is None:
        raise ValueError("This quiz has no questions.")

    attempt.asked_ids.append(question.id)
    attempt.current_id = question.id
    _ATTEMPTS[attempt.id] = attempt
    logger.info("Attempt %s started on quiz %s at '%s'", attempt.id, quiz.id, question.difficulty)
    return attempt, question


def submit_answer(
    quiz: StoredQuiz,
    attempt: Attempt,
    selected: Union[str, list[str]],
) -> tuple[AnswerRecord, GeneratedQuestion | None]:
    """Grade the current question, move the ladder, and serve the next one.

    Returns the graded record and the next question, or None once the attempt
    has reached the quiz length.
    """
    if attempt.is_finished:
        raise ValueError("This attempt is already finished.")
    if attempt.current_id is None:
        raise ValueError("This attempt has no question waiting to be answered.")

    current = next((q for q in quiz.pool if q.id == attempt.current_id), None)
    if current is None:
        raise ValueError("The question being answered is no longer in the quiz.")

    was_correct = _is_correct(selected, current.correct_answer)
    record = AnswerRecord(
        question_id=current.id,
        question=current.question,
        difficulty=current.difficulty,
        bloom_level=current.bloom_level,
        selected=selected,
        correct_answer=current.correct_answer,
        was_correct=was_correct,
    )
    attempt.answers.append(record)

    before = attempt.ladder.difficulty
    attempt.ladder = attempt.ladder.record(was_correct)
    if attempt.ladder.difficulty != before:
        logger.info(
            "Attempt %s: %s -> %s after %d answers",
            attempt.id, before, attempt.ladder.difficulty, len(attempt.answers),
        )

    if len(attempt.answers) >= quiz.quiz_length:
        attempt.finished_at = datetime.now(timezone.utc)
        attempt.current_id = None
        logger.info(
            "Attempt %s finished: %d/%d, settled at '%s'",
            attempt.id, attempt.score, quiz.quiz_length, attempt.ladder.difficulty,
        )
        return record, None

    nxt = _pick_question(quiz, attempt)
    if nxt is None:
        # Only reachable if the pool was short AND every difficulty is exhausted.
        attempt.finished_at = datetime.now(timezone.utc)
        attempt.current_id = None
        logger.error("Attempt %s ran out of questions early", attempt.id)
        return record, None

    attempt.asked_ids.append(nxt.id)
    attempt.current_id = nxt.id
    return record, nxt
