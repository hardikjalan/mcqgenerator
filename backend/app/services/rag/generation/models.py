"""
models.py
=========
Data contracts and configurations for Layer 6: MCQ Generation.
"""

from __future__ import annotations

from typing import Union, Literal
from pydantic import BaseModel, Field


BloomLevel = Literal["Remember", "Understand", "Apply", "Analyze", "Evaluate", "Create"]


class Evidence(BaseModel):
    source_id: str
    parent_id: str
    quote: str = Field(min_length=10, max_length=2000)
    file_name: str = ""
    page: int | None = None
    pages: list[int] = Field(default_factory=list)


class GeneratedQuestion(BaseModel):
    """Represents a single generated assessment question."""

    id: int = Field(description="Sequential 1-based question number")
    question: str = Field(description="The prompt or question text")
    options: list[str] = Field(description="The list of answer options (4 for single/multiple, 2 for true/false)")
    correct_answer: Union[str, list[str]] = Field(
        description="The exact correct answer text string, or list of strings for multiple choice"
    )
    question_type: Literal["single", "multiple", "truefalse"] = Field(
        default="single",
        description="Question format: single, multiple, or truefalse"
    )
    explanation: str = ""
    evidence: list[Evidence] = Field(default_factory=list)
    bloom_level: BloomLevel = "Remember"
    bloom_rationale: str = ""
    difficulty: int = Field(default=1, ge=1, le=5)
    topic: str = ""


class QuestionReview(BaseModel):
    id: int
    supported: bool
    reason: str
    bloom_level: BloomLevel
    bloom_rationale: str
    difficulty: int = Field(ge=1, le=5)
    topic: str


class ReviewBatch(BaseModel):
    reviews: list[QuestionReview]


class GeneratedQuiz(BaseModel):
    """Container holding the complete list of generated questions."""

    questions: list[GeneratedQuestion] = Field(
        description="The complete list of generated questions matching requested count"
    )


class GenerationConfig(BaseModel):
    """Configuration options for Gemini question generation."""

    model_name: str = "gemini-3.5-flash-lite"
    fallback_model_name: str | None = "gemini-3.8-flash"
    temperature: float = 0.2
    request_timeout_ms: int = 60000
