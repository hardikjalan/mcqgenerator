"""
cleaning — Centralized text normalization for RAG documents
============================================================

Public API::

    from app.services.rag.processing.cleaning import DocumentCleaner

    cleaner = DocumentCleaner()
    cleaned = cleaner.clean_documents(raw_docs)
"""

from app.services.rag.processing.cleaning.cleaner import (  # noqa: F401
    DocumentCleaner,
    TextCleaner,
)
from app.services.rag.processing.cleaning.rules import (  # noqa: F401
    normalize_line_endings,
    normalize_unicode,
    remove_control_characters,
    normalize_whitespace,
)

__all__ = [
    "DocumentCleaner",
    "TextCleaner",
    "normalize_line_endings",
    "normalize_unicode",
    "remove_control_characters",
    "normalize_whitespace",
]
