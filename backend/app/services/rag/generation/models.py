"""
models.py
=========
Data contracts and configurations for Layer 6: MCQ Generation.
"""

from __future__ import annotations

from typing import Literal, Union, get_args
from pydantic import BaseModel, Field


# Bloom's revised taxonomy, restricted to the levels a multiple-choice question
# can honestly test. "Create" is omitted deliberately: it requires the student
# to produce something original, which no fixed set of options can assess, so
# including it would only invite mislabelled questions. "Evaluate" is kept
# because an MCQ can legitimately ask which of several judgements is best
# supported.
#
# Declared as a Literal so it becomes an enum in the JSON schema handed to
# Gemini via response_schema. The model is then constrained to one of these
# five strings — an invalid level cannot come back and need not be validated.
BloomLevel = Literal["remember", "understand", "apply", "analyze", "evaluate"]

# Same five values in increasing order of cognitive demand, for anything that
# needs to iterate or sort them. Derived from the Literal above so the two can
# never drift apart.
BLOOM_LEVELS: tuple[BloomLevel, ...] = get_args(BloomLevel)


class GeneratedQuestion(BaseModel):
    """Represents a single generated assessment question."""

    id: int = Field(description="Sequential 1-based question number")
    question: str = Field(description="The prompt or question text")
    options: list[str] = Field(description="The list of answer options (4 for single/multiple, 2 for true/false)")
    correct_answer: Union[str, list[str]] = Field(
        description="The exact correct answer text string, or list of strings for multiple choice"
    )
    question_type: str = Field(
        default="single",
        description="Question format: single, multiple, or truefalse"
    )
    bloom_level: BloomLevel = Field(
        description=(
            "Bloom's taxonomy level describing the cognitive work the student must "
            "do to answer, not how advanced the subject matter is"
        )
    )


class GeneratedQuiz(BaseModel):
    """Container holding the complete list of generated questions."""

    questions: list[GeneratedQuestion] = Field(
        description="The complete list of generated questions matching requested count"
    )


class GenerationConfig(BaseModel):
    """Configuration options for Gemini question generation."""

    model_name: str = "gemini-2.5-flash"
    temperature: float = 0.2
