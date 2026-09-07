"""
base.py
=======
The generation contract, and what a generated question is.

A question is not just text: it carries the chunks it was written from. That
turns "the model said so" into something checkable — a teacher can see the
passage, and the validator can refuse a question whose answer does not appear
in the material it claims to come from. Retrieval-augmented generation without
that link is just generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from app.services.rag.ingestion.exceptions import IngestionError


class GenerationUnavailableError(IngestionError):
    """Raised when no generation provider is configured."""

    def __init__(self) -> None:
        super().__init__(
            "Question generation isn't switched on for this deployment.",
        )


class GenerationFailedError(IngestionError):
    """Raised when the model could not produce usable questions."""

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            "Could not write questions from these documents. Try again, or "
            "upload material that covers the topics more directly.",
            detail=reason,
        )


class NoMaterialError(IngestionError):
    """Raised when nothing in the uploads is relevant to the quiz topics."""

    def __init__(self, topics: str) -> None:
        super().__init__(
            f"Nothing in the uploaded material covers “{topics}” closely "
            "enough to write questions from. Check the topics, or upload "
            "material that covers them.",
        )


@dataclass
class MCQ:
    """One multiple-choice question, with its evidence."""

    question: str
    options: list[str]
    correct_index: int
    explanation: str = ""
    citations: list[str] = field(default_factory=list)
    source_chunk_ids: list[str] = field(default_factory=list)

    @property
    def correct_answer(self) -> str:
        return self.options[self.correct_index]


@dataclass
class QuizBrief:
    """What the faculty member asked for, in the shape generation needs."""

    subject: str
    topics: str
    objective: str
    grade_level: str
    count: int


@runtime_checkable
class QuestionGenerator(Protocol):
    """Anything that can write questions from source passages."""

    name: str

    def generate(self, brief: QuizBrief, passages: list[str], count: int) -> list[MCQ]:
        """Write *count* questions using only *passages*."""
        ...
