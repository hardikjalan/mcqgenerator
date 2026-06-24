"""
gemini_ocr.py
=============
Thin wrapper around the Google Gemini API for image text extraction (OCR).

Includes retry logic with exponential backoff for transient API errors.
Known/expected API failures (503, quota, rate-limit) are logged as concise
warnings without stack traces. Unexpected errors get full tracebacks.

Raises structured OCRError / DocumentProcessingError subclasses on failure.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from google import genai
from google.genai import types
from dotenv import load_dotenv
from exceptions import OCRError
from logger import get_logger, is_debug_mode

logger = get_logger(__name__)

# ── Environment setup ─────────────────────────────────────────────────────────
# __file__ is: .../backend/extractors/gemini_ocr.py
# .env.local lives at: .../mcqgenerator/.env.local (3 levels up)
_env_path = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    ".env.local",
)
load_dotenv(dotenv_path=_env_path)

_api_key = os.getenv("GEMINI_API_KEY")
if not _api_key:
    logger.warning("[OCR] GEMINI_API_KEY not found — OCR will be unavailable")
else:
    logger.debug("[OCR] GEMINI_API_KEY loaded from: %s", _env_path)

_client = genai.Client(api_key=_api_key) if _api_key else None

GEMINI_MODEL = "gemini-2.5-flash"
MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 1.5  # multiplied by attempt number

_OCR_PROMPT = (
    "Extract all readable text from this image. "
    "If the image contains educational content such as diagrams, charts, tables, "
    "flowcharts, or technical illustrations, provide a concise explanation of the "
    "content as well."
)

# Known transient/quota error substrings — log as warning, no stack trace
_EXPECTED_ERROR_PATTERNS = (
    "503",
    "quota",
    "rate limit",
    "resource_exhausted",
    "service unavailable",
    "internal error",
    "overloaded",
    "deadline",
)


def _is_expected_api_error(exc: Exception) -> bool:
    """Return True if the exception is a known transient or quota API error."""
    msg = str(exc).lower()
    return any(pattern in msg for pattern in _EXPECTED_ERROR_PATTERNS)


def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Send image bytes to Gemini and return extracted text.

    Retries up to MAX_RETRIES times on transient errors with linear backoff.

    Parameters
    ----------
    image_bytes : bytes
        Raw image data.
    mime_type : str
        MIME type of the image (e.g. "image/jpeg", "image/png").

    Returns
    -------
    str
        Extracted text, or an empty string if no text was found.

    Raises
    ------
    OCRError
        If the API key is not configured, or all retry attempts fail.
    """
    if not _client:
        logger.error("[OCR] No API key configured — cannot perform OCR")
        raise OCRError("GEMINI_API_KEY is not configured. Cannot perform OCR.")

    if not image_bytes:
        logger.debug("[OCR] Called with empty image bytes — skipping")
        return ""

    last_exc: Exception | None = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            if attempt > 1:
                logger.info("[OCR] Retry %d/%d...", attempt, MAX_RETRIES)

            response = _client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                    _OCR_PROMPT,
                ],
            )

            if response and response.text:
                extracted = response.text.strip()
                logger.debug("[OCR] Gemini returned %d chars", len(extracted))
                return extracted

            logger.debug("[OCR] Gemini returned empty response")
            return ""

        except Exception as exc:
            last_exc = exc
            if _is_expected_api_error(exc):
                # Known transient / quota error — concise warning, no stack trace
                logger.warning(
                    "[OCR] API error (attempt %d/%d): %s",
                    attempt, MAX_RETRIES, _summarize_error(exc),
                )
            else:
                # Unexpected error — full trace, but only on final attempt to avoid spam
                if attempt == MAX_RETRIES:
                    logger.error(
                        "[OCR] Unexpected API error after %d attempts: %s",
                        MAX_RETRIES, exc,
                        exc_info=is_debug_mode(),
                    )
                else:
                    logger.warning(
                        "[OCR] Unexpected error (attempt %d/%d): %s — retrying",
                        attempt, MAX_RETRIES, exc,
                    )

            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)

    # All retries exhausted
    raise OCRError(detail=_summarize_error(last_exc)) from last_exc


def _summarize_error(exc: Exception | None) -> str:
    """Return a concise single-line summary of an exception for log messages."""
    if exc is None:
        return "unknown error"
    msg = str(exc)
    # Truncate very long exception messages (e.g. full API response bodies)
    return msg[:200] + "..." if len(msg) > 200 else msg
