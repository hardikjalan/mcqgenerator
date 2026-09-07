"""
RAG Layer 4 — Generation
========================

Optional, like every layer above it. ``get_generator()`` returns None when no
key is configured, and everything else still works — files are read, chunked
and indexed, there is simply nothing to write questions with.

Public API::

    from app.services.rag.generation import get_generator

    generator = get_generator()
    questions = generator.generate(brief, passages, count=5)
"""

from app.services.rag.generation.base import (  # noqa: F401
    MCQ,
    GenerationFailedError,
    GenerationUnavailableError,
    NoMaterialError,
    QuestionGenerator,
    QuizBrief,
)
from app.services.rag.generation.gemini import GeminiGenerator  # noqa: F401
from app.services.rag.generation.validator import validate  # noqa: F401

__all__ = [
    "get_generator",
    "MCQ",
    "QuizBrief",
    "QuestionGenerator",
    "GeminiGenerator",
    "GenerationUnavailableError",
    "GenerationFailedError",
    "NoMaterialError",
    "validate",
]


def get_generator() -> "QuestionGenerator | None":
    """Return the configured question generator, or None if there isn't one."""
    from app import config

    if not config.generation_enabled():
        return None
    return GeminiGenerator(
        api_key=config.GEMINI_API_KEY,
        model=config.GEMINI_GENERATION_MODEL,
    )
