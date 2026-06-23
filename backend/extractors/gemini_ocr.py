"""
gemini_ocr.py
=============
Thin wrapper around the Google Gemini API for image text extraction (OCR).

Raises structured OCRError / DocumentProcessingError subclasses instead of
swallowing exceptions silently.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from google import genai
from google.genai import types
from dotenv import load_dotenv
from exceptions import OCRError
from logger import get_logger

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
    logger.warning("GEMINI_API_KEY not found. Searched at: %s", _env_path)
else:
    logger.info("GEMINI_API_KEY loaded successfully from: %s", _env_path)

_client = genai.Client(api_key=_api_key) if _api_key else None

GEMINI_MODEL = "gemini-2.0-flash"

_OCR_PROMPT = (
    "Extract all readable text from this image. "
    "If the image contains educational content such as diagrams, charts, tables, flowcharts, or technical illustrations, provide a concise explanation of the content as well."
)


def extract_text_from_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """
    Send image bytes to Gemini and return extracted text.

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
        If the Gemini API key is not configured or the API call fails.
    """
    if not _client:
        logger.error("Gemini OCR attempted without a configured API key.")
        raise OCRError("GEMINI_API_KEY is not configured. Cannot perform OCR.")

    if not image_bytes:
        logger.warning("extract_text_from_image called with empty image_bytes")
        return ""

    try:
        response = _client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                _OCR_PROMPT,
            ],
        )
        if response and response.text:
            extracted = response.text.strip()
            logger.debug("Gemini OCR returned %d chars", len(extracted))
            return extracted
        logger.debug("Gemini OCR returned empty response")
        return ""
    except Exception as e:
        logger.error("Gemini OCR API error: %s", e, exc_info=True)
        raise OCRError(detail=str(e)) from e
