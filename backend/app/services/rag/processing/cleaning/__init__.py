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
    layout_aware_cleaner,
)
from app.services.rag.processing.cleaning.rules import (  # noqa: F401
    normalize_line_endings,
    normalize_unicode,
    remove_control_characters,
    normalize_whitespace,
    repair_line_wraps,
)

__all__ = [
    "DocumentCleaner",
    "TextCleaner",
    "layout_aware_cleaner",
    "repair_line_wraps",
    "normalize_line_endings",
    "normalize_unicode",
    "remove_control_characters",
    "normalize_whitespace",
]
