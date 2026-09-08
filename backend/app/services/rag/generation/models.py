"""
models.py
=========
Data contracts and configurations for Layer 6: MCQ Generation.
"""

from __future__ import annotations

from typing import Union
from pydantic import BaseModel, Field


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


class GeneratedQuiz(BaseModel):
    """Container holding the complete list of generated questions."""

    questions: list[GeneratedQuestion] = Field(
        description="The complete list of generated questions matching requested count"
    )


class GenerationConfig(BaseModel):
    """Configuration options for Gemini question generation."""

    model_name: str = "gemini-2.5-flash"
    temperature: float = 0.2
