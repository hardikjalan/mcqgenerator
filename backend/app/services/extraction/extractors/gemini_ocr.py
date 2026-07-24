"""
gemini_ocr.py
=============
Thin wrapper around the Google Gemini API for image text extraction (OCR).

Retry strategy: up to 4 total attempts with delays of 2 s, 5 s, and 10 s.
If all Gemini attempts fail, falls back to local Tesseract OCR (if installed).

Known/expected API failures (503, quota, rate-limit) are logged as concise
warnings without stack traces. Unexpected errors get full tracebacks.

Raises structured OCRError / DocumentProcessingError subclasses on failure.
"""

import io
import os
import time


from google import genai
from google.genai import types
from app.core.exceptions import OCRError
from app.core.logger import get_logger, is_debug_mode
from app.core.config import ENV_PATH, GEMINI_API_KEY, TESSERACT_CMD_PATH

logger = get_logger(__name__)

# ── Environment setup ─────────────────────────────────────────────────────────
# The .env read itself happens once in app/core/config.py — importing it here is
# what triggers the load.
_api_key = GEMINI_API_KEY
if not _api_key:
    logger.warning("[OCR] GEMINI_API_KEY not found — OCR will be unavailable")
else:
    logger.debug("[OCR] GEMINI_API_KEY loaded from: %s", ENV_PATH)

_client = genai.Client(api_key=_api_key) if _api_key else None

GEMINI_MODEL = "gemini-2.5-flash"

# Retry delays in seconds: wait 2 s before attempt 2, 5 s before attempt 3,
# 10 s before attempt 4. Length also defines the number of retries.
RETRY_DELAYS = [2.0, 5.0, 10.0]

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


def _summarize_error(exc: Exception | None) -> str:
    """Return a concise single-line summary of an exception for log messages."""
    if exc is None:
        return "unknown error"
    msg = str(exc)
    # Truncate very long exception messages (e.g. full API response bodies)
    return msg[:200] + "..." if len(msg) > 200 else msg


def _tesseract_available(cmd: str) -> bool:
    """Return True if the given Tesseract executable path/command is accessible."""
    import shutil
    # Absolute / relative path — check the file directly
    if os.sep in cmd or "/" in cmd:
        return os.path.isfile(cmd)
    # Short name (e.g. "tesseract") — check system PATH
    return shutil.which(cmd) is not None


def _extract_text_via_tesseract(image_bytes: bytes) -> str:
    """
    Fallback OCR using local Tesseract (via pytesseract).

    Resolves the Tesseract binary in order:
      1. TESSERACT_CMD_PATH environment variable
      2. Default Windows install path: C:\\Program Files\\Tesseract-OCR\\tesseract.exe
      3. System PATH (pytesseract default)

    Parameters
    ----------
    image_bytes : bytes
        Raw image data.

    Returns
    -------
    str
        Extracted text, or empty string if nothing was found.

    Raises
    ------
    OCRError
        If pytesseract is not installed, Tesseract binary is not found,
        or extraction fails unexpectedly.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        raise OCRError(
            "pytesseract is not installed. Run: pip install pytesseract",
        )

    # ── Resolve Tesseract binary path ─────────────────────────────────────────
    tess_cmd = TESSERACT_CMD_PATH
    if not tess_cmd:
        default_win_path = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        if os.path.isfile(default_win_path):
            tess_cmd = default_win_path

    if tess_cmd:
        pytesseract.pytesseract.tesseract_cmd = tess_cmd

    effective_cmd = pytesseract.pytesseract.tesseract_cmd
    if not _tesseract_available(effective_cmd):
        raise OCRError(
            "Tesseract binary not found. "
            "Install from https://github.com/UB-Mannheim/tesseract/wiki "
            "or set TESSERACT_CMD_PATH in backend/.env."
        )

    try:
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        return text.strip() if text else ""
    except Exception as e:
        raise OCRError(f"Tesseract extraction failed: {e}") from e


def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Send image bytes to Gemini and return extracted text.

    Retries with delays of 2 s, 5 s, and 10 s between attempts (4 total).
    If all Gemini attempts fail, falls back to local Tesseract OCR.

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
        If the API key is not configured, all retry attempts fail, and
        Tesseract fallback also fails or is unavailable.
    """
    if not _client:
        logger.error("[OCR] No API key configured — cannot perform OCR")
        raise OCRError("GEMINI_API_KEY is not configured. Cannot perform OCR.")

    if not image_bytes:
        logger.debug("[OCR] Called with empty image bytes — skipping")
        return ""

    last_exc: Exception | None = None
    total_attempts = len(RETRY_DELAYS) + 1  # 4 attempts total

    for attempt in range(1, total_attempts + 1):
        try:
            if attempt > 1:
                logger.info(
                    "[OCR] Retry %d/%d...",
                    attempt - 1, len(RETRY_DELAYS),
                )

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
                logger.warning(
                    "[OCR] API error (attempt %d/%d): %s",
                    attempt, total_attempts, _summarize_error(exc),
                )
            else:
                if attempt == total_attempts:
                    logger.error(
                        "[OCR] Unexpected API error after %d attempts: %s",
                        total_attempts, exc,
                        exc_info=is_debug_mode(),
                    )
                else:
                    logger.warning(
                        "[OCR] Unexpected error (attempt %d/%d): %s — retrying",
                        attempt, total_attempts, exc,
                    )

            # Sleep before next attempt using the configured delay list
            if attempt < total_attempts:
                delay = RETRY_DELAYS[attempt - 1]
                logger.debug("[OCR] Waiting %.0fs before next attempt...", delay)
                time.sleep(delay)

    # ── All Gemini attempts exhausted — try Tesseract fallback ───────────────
    logger.warning(
        "[OCR] All %d Gemini attempts failed (%s) — trying Tesseract fallback...",
        total_attempts, _summarize_error(last_exc),
    )
    try:
        text = _extract_text_via_tesseract(image_bytes)
        logger.info("[OCR] Tesseract fallback succeeded — %d chars", len(text))
        return text
    except OCRError as tess_err:
        logger.error("[OCR] Tesseract fallback failed: %s", tess_err)
        # Raise the original Gemini error so callers get the right context
        raise OCRError(detail=_summarize_error(last_exc)) from last_exc
