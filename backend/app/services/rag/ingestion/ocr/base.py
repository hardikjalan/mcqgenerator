"""
base.py
=======
The OCR contract.

One method, taking image bytes and returning text. Deliberately narrow: OCR is
a detail of how a page becomes text, and no caller should have to know which
provider answered or how it was configured.

``OCRUnavailableError`` is separate from ``OCRFailedError`` because the two
mean different things to the person who uploaded the file. Unavailable is a
configuration state — nobody set an API key — and no amount of retrying will
change it. Failed is transient.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.rag.ingestion.exceptions import IngestionError


class OCRUnavailableError(IngestionError):
    """Raised when no OCR provider is configured."""

    def __init__(self) -> None:
        super().__init__(
            "Reading text from images isn't switched on. Upload a PDF, DOCX or "
            "PPTX, or paste the text instead.",
        )


class OCRFailedError(IngestionError):
    """Raised when a configured provider could not read an image."""

    def __init__(self, file_name: str, reason: str = "") -> None:
        super().__init__(
            f"Could not read the text in {file_name}. If it is a photo, a "
            "sharper or better-lit version usually works.",
            detail=reason,
        )


@runtime_checkable
class OCRProvider(Protocol):
    """Anything that can turn an image into text."""

    name: str

    def extract_text(self, image: bytes, *, mime_type: str, file_name: str) -> str:
        """Return the text visible in *image*, or an empty string if none."""
        ...
