"""
RAG Layer 1 — OCR
=================

Optional. With no provider configured the pipeline still runs: images are
refused with a clear message and scanned PDFs fail as empty, while every
text-bearing format works exactly as before.

Public API::

    from app.services.rag.ingestion.ocr import get_provider

    provider = get_provider()          # None when unconfigured
    text = provider.extract_text(png_bytes, mime_type="image/png", file_name="x.png")

``get_provider`` is a function rather than a module-level instance so tests can
monkeypatch it, and so a key added to the environment takes effect without
reimporting half the package.
"""

from app.services.rag.ingestion.ocr.base import (  # noqa: F401
    OCRFailedError,
    OCRProvider,
    OCRUnavailableError,
)
from app.services.rag.ingestion.ocr.gemini import GeminiOCR  # noqa: F401

__all__ = [
    "get_provider",
    "GeminiOCR",
    "OCRProvider",
    "OCRUnavailableError",
    "OCRFailedError",
]


def get_provider() -> "OCRProvider | None":
    """Return the configured OCR provider, or None if there isn't one."""
    from app import config

    if not config.ocr_enabled():
        return None
    return GeminiOCR(api_key=config.GEMINI_API_KEY, model=config.GEMINI_OCR_MODEL)
