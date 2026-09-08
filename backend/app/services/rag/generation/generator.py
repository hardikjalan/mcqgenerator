"""
generator.py
============
Layer 6 Coordinator: MCQGenerator.
Uses Google Gemini to generate assessment questions grounded strictly
in Layer 5 retrieved parent contexts.
"""

from __future__ import annotations

import logging
import os
import time
from google import genai
from google.genai import errors, types

from app.schemas import QuizConfig
from app.services.rag.retrieval.models import RetrievedParentContext
from app.services.rag.generation.models import (
    GeneratedQuestion,
    GeneratedQuiz,
    GenerationConfig,
)

logger = logging.getLogger(__name__)


class MCQGenerator:
    """Generates RAG-grounded multiple-choice questions via Google Gemini."""

    def __init__(
        self,
        config: GenerationConfig | None = None,
        client: genai.Client | None = None,
    ) -> None:
        self.config = config or GenerationConfig()
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if client is not None:
            self.client = client
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()

    def generate_assessment(
        self,
        contexts: list[RetrievedParentContext],
        quiz_config: QuizConfig,
    ) -> list[GeneratedQuestion]:
        """Generate questions grounded strictly in the retrieved contexts.

        Parameters
        ----------
        contexts : list[RetrievedParentContext]
            Retrieved parent context chunks from Layer 5.
        quiz_config : QuizConfig
            Teacher configuration (subject, topics, objective, question count, type).

        Returns
        -------
        list[GeneratedQuestion]
            Exactly `quiz_config.questionCount` generated questions.

        Raises
        ------
        ValueError
            If retrieved contexts are empty or if the model fails to return the
            exact required question count after retry.
        """
        if not contexts:
            raise ValueError("Cannot generate questions: no retrieved context provided.")

        target_count = quiz_config.questionCount
        if target_count < 1:
            raise ValueError("Target question count must be at least 1.")

        # 1. Assemble context blocks
        context_blocks = []
        for i, ctx in enumerate(contexts, start=1):
            source_info = f"Source: {ctx.file_name}"
            if ctx.page_or_slide_num:
                source_info += f", Page/Slide: {ctx.page_or_slide_num}"
            if ctx.heading:
                source_info += f", Section: {ctx.heading}"
            context_blocks.append(f"--- Context Passage {i} [{source_info}] ---\n{ctx.content}")

        combined_context = "\n\n".join(context_blocks)

        # 2. Build instructions based on question type
        q_type = (quiz_config.questionType or "single").lower()
        if q_type == "single":
            type_rules = (
                "Format: SINGLE CHOICE questions only.\n"
                "- Every question must have EXACTLY 4 options.\n"
                "- Exactly 1 option must be correct.\n"
                "- `correct_answer` must be a single string matching the exact text of the correct option."
            )
        elif q_type == "multiple":
            type_rules = (
                "Format: MULTIPLE CHOICE (multi-select) questions only.\n"
                "- Every question must have EXACTLY 4 options.\n"
                "- At least 2 options must be correct.\n"
                "- `correct_answer` must be a list of strings matching the exact text of each correct option."
            )
        elif q_type == "truefalse":
            type_rules = (
                "Format: TRUE / FALSE questions only.\n"
                "- Every question must have EXACTLY 2 options: ['True', 'False'].\n"
                "- `correct_answer` must be a single string: either 'True' or 'False'."
            )
        else:  # 'all'
            type_rules = (
                "Format: MIXED format questions (balanced mixture of single choice, multiple choice, and true/false).\n"
                "- For single choice: exactly 4 options, 1 correct answer (string).\n"
                "- For multiple choice: exactly 4 options, 2+ correct answers (list of strings).\n"
                "- For true/false: exactly 2 options ['True', 'False'], 1 correct answer (string)."
            )

        prompt = (
            f"You are an expert assessment author. Generate an academic assessment based on the provided reference material.\n\n"
            f"=== TARGET PARAMETERS ===\n"
            f"Subject: {quiz_config.subjectName}\n"
            f"Target Audience / Grade Level: {quiz_config.gradeLevel}\n"
            f"Topics to Cover: {quiz_config.topicsCovered}\n"
            f"Learning Objective: {quiz_config.learningObjective}\n"
            f"Total Number of Questions: EXACTLY {target_count}\n\n"
            f"=== QUESTION FORMAT RULES ===\n"
            f"{type_rules}\n\n"
            f"=== STRICT GENERATION CONSTRAINTS ===\n"
            f"1. You MUST generate questions grounded ONLY in the reference context provided below.\n"
            f"2. Do NOT invent information, facts, or assumptions outside the reference context.\n"
            f"3. You MUST generate EXACTLY {target_count} questions. Returning fewer or more than {target_count} is invalid.\n"
            f"4. For each question, output ONLY:\n"
            f"   - `id`: sequential integer (1 to {target_count})\n"
            f"   - `question`: clear question text\n"
            f"   - `options`: array of choices\n"
            f"   - `correct_answer`: correct choice text or array of choices\n"
            f"   - `question_type`: 'single', 'multiple', or 'truefalse'\n"
            f"5. Do NOT include explanations, rationale, or markdown commentary.\n\n"
            f"=== REFERENCE CONTEXT ===\n"
            f"{combined_context}\n"
        )

        # 3. Call Gemini with structured response schema
        quiz = self._call_gemini(prompt)

        # 4. Strict question count verification & retry
        if len(quiz.questions) != target_count:
            logger.warning(
                "Gemini generated %d questions, but requested count is %d. Retrying once with corrective prompt...",
                len(quiz.questions),
                target_count,
            )
            corrective_prompt = (
                f"{prompt}\n\n"
                f"CRITICAL ERROR IN PREVIOUS ATTEMPT: You generated {len(quiz.questions)} questions. "
                f"You MUST generate EXACTLY {target_count} questions. Double-check your output count."
            )
            quiz = self._call_gemini(corrective_prompt)

            if len(quiz.questions) != target_count:
                error_msg = (
                    f"Question count mismatch: requested {target_count} questions, "
                    f"but model produced {len(quiz.questions)} questions."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

        # Ensure IDs are 1-indexed sequentially
        for idx, q in enumerate(quiz.questions, start=1):
            q.id = idx

        return quiz.questions

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        """Check if an exception is a transient 503 (Unavailable) or 429 (Rate Limit)."""
        if isinstance(exc, errors.APIError):
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            if code in (503, 429) or status in ("UNAVAILABLE", "RESOURCE_EXHAUSTED"):
                return True
            msg = (getattr(exc, "message", "") or str(exc)).upper()
            if any(term in msg for term in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND")):
                return True
            return False

        err_str = str(exc).upper()
        return any(term in err_str for term in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND"))

    def _call_gemini(self, prompt: str) -> GeneratedQuiz:
        """Execute generate_content against Google Gemini with JSON schema enforcement.

        Retries on transient 503 (Unavailable) and 429 (Rate Limit) errors using
        exponential backoff (2s, 4s, 8s) up to 3 retries. Normal validation,
        auth, or bad-request errors are NOT retried.
        """
        delays = [2.0, 4.0, 8.0]
        last_exception: Exception | None = None

        for attempt in range(len(delays) + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.config.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=self.config.temperature,
                        response_mime_type="application/json",
                        response_schema=GeneratedQuiz,
                    ),
                )

                if response.parsed and isinstance(response.parsed, GeneratedQuiz):
                    return response.parsed

                # Fallback to direct Pydantic JSON parsing
                if response.text:
                    return GeneratedQuiz.model_validate_json(response.text)

                raise RuntimeError("Empty or unparseable response from Gemini generation API.")

            except Exception as exc:
                if not self._is_transient_error(exc):
                    # Do not retry validation, auth, or client bad-request errors
                    raise

                last_exception = exc
                if attempt < len(delays):
                    delay = delays[attempt]
                    logger.warning(
                        "Gemini API transient error on attempt %d/%d: %s. Retrying in %.1fs...",
                        attempt + 1,
                        len(delays),
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "Gemini API transient error persisted after %d retries: %s",
                        len(delays),
                        exc,
                    )

        raise RuntimeError(
            "Gemini AI generation service is temporarily unavailable due to high demand. "
            "Please try again in a few moments."
        ) from last_exception
