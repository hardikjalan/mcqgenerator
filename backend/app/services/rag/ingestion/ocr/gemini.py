"""
gemini.py
=========
OCR via Gemini's vision models.

The prompt matters more than it looks. A vision model asked to "describe this
image" will happily narrate one, and that narration would flow downstream into
quiz questions as though it were course material. So the instruction is to
transcribe and nothing else, and to return an empty response when there is no
text — which the caller then treats as an empty page rather than as content.
"""

from __future__ import annotations

from app.services.rag.ingestion.ocr.base import OCRFailedError

_PROMPT = (
    "Transcribe all text visible in this image, exactly as written. "
    "Preserve reading order, line breaks and any list or table structure. "
    "Do not describe the image, do not summarise, do not add commentary, and "
    "do not translate. If the image contains no legible text, reply with "
    "nothing at all."
)

# A model sometimes narrates anyway when a page is blank. These are the shapes
# it uses; treated as "no text" rather than as content.
_REFUSAL_MARKERS = (
    "no legible text",
    "no text visible",
    "contains no text",
    "image does not contain",
    "unable to transcribe",
)


class GeminiOCR:
    """Vision OCR backed by the ``google-genai`` SDK."""

    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model
        self._client = None  # built lazily; constructing it costs a handshake

    def extract_text(self, image: bytes, *, mime_type: str, file_name: str) -> str:
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise OCRFailedError(
                file_name, reason="google-genai is not installed"
            ) from exc

        if self._client is None:
            self._client = genai.Client(api_key=self._api_key)

        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=[
                    types.Part.from_bytes(data=image, mime_type=mime_type),
                    _PROMPT,
                ],
            )
        except Exception as exc:
            raise OCRFailedError(file_name, reason=f"{type(exc).__name__}: {exc}") from exc

        return _clean(response.text or "")


def _clean(text: str) -> str:
    """Drop the model's own commentary about there being nothing to read."""
    stripped = text.strip()
    lowered = stripped.lower()

    if any(marker in lowered for marker in _REFUSAL_MARKERS) and len(stripped) < 200:
        return ""
    return stripped
