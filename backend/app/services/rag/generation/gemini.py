"""
gemini.py
=========
Question generation with Gemini, using structured output.

The model is asked for JSON matching a fixed schema rather than for prose that
we then parse. Parsing prose out of a chat response works until the day it
politely explains what it is about to do first.

Structured output guarantees *shape*, not *sense* — the schema cannot express
"the correct answer must actually be correct". Everything that matters is
checked afterwards in ``validator.py``.

Questions are requested in small batches. Asking for forty at once produces
visibly worse questions towards the end of the list, and one refusal loses the
lot.
"""

from __future__ import annotations

import json

from app import config
from app.services.rag.generation.base import MCQ, GenerationFailedError, QuizBrief
from app.services.rag.generation.prompt import SYSTEM_INSTRUCTION, build_prompt

# The shape asked of the model. Kept as a plain dict rather than a Pydantic
# model so it is obvious what the model actually sees.
_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "question": {"type": "STRING"},
            "options": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "minItems": 4,
                "maxItems": 4,
            },
            "correct_index": {"type": "INTEGER"},
            "explanation": {"type": "STRING"},
            "evidence": {
                "type": "ARRAY",
                "items": {"type": "STRING"},
                "description": "Exact sentences quoted from the passages",
            },
            "passage_numbers": {"type": "ARRAY", "items": {"type": "INTEGER"}},
        },
        "required": ["question", "options", "correct_index", "evidence"],
    },
}


class GeminiGenerator:
    """Writes multiple-choice questions from source passages."""

    name = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        temperature: float | None = None,
        batch_size: int | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._temperature = temperature if temperature is not None else config.GENERATION_TEMPERATURE
        self._batch_size = batch_size or config.GENERATION_BATCH_SIZE
        self._client = None

    def generate(self, brief: QuizBrief, passages: list[str], count: int) -> list[MCQ]:
        """Write up to *count* questions, in batches."""
        questions: list[MCQ] = []

        remaining = count
        while remaining > 0:
            batch = min(self._batch_size, remaining)
            questions.extend(self._generate_batch(brief, passages, batch))
            remaining -= batch

        return questions

    # ── Internal ──────────────────────────────────────────────────────────

    def _generate_batch(self, brief: QuizBrief, passages: list[str], count: int) -> list[MCQ]:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise GenerationFailedError("google-genai is not installed") from exc

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=build_prompt(brief, passages, count),
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=self._temperature,
                    response_mime_type="application/json",
                    response_schema=_SCHEMA,
                ),
            )
        except Exception as exc:  # noqa: BLE001 - SDK raises many types
            raise GenerationFailedError(f"{type(exc).__name__}: {exc}") from exc

        return _parse(response.text or "", passages)


def _parse(raw: str, passages: list[str]) -> list[MCQ]:
    """Turn the model's JSON into MCQ objects.

    A batch that comes back unparseable is dropped rather than raised on: the
    other batches may be fine, and returning three good questions beats
    returning an error because the fourth request misbehaved.
    """
    try:
        payload = json.loads(raw)
    except ValueError:
        print(f"[generation] unparseable response: {raw[:200]}")
        return []

    if not isinstance(payload, list):
        return []

    questions: list[MCQ] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            questions.append(
                MCQ(
                    question=str(item["question"]).strip(),
                    options=[str(option).strip() for option in item["options"]],
                    correct_index=int(item["correct_index"]),
                    explanation=str(item.get("explanation", "")).strip(),
                    citations=[str(quote) for quote in item.get("evidence", [])],
                    source_chunk_ids=_passage_ids(item.get("passage_numbers"), passages),
                )
            )
        except (KeyError, TypeError, ValueError) as exc:
            print(f"[generation] skipping malformed question: {exc}")

    return questions


def _passage_ids(numbers: object, passages: list[str]) -> list[str]:
    """Map the model's 1-based passage numbers onto indexes we can resolve."""
    if not isinstance(numbers, list):
        return []
    return [
        str(number)
        for number in numbers
        if isinstance(number, int) and 1 <= number <= len(passages)
    ]
