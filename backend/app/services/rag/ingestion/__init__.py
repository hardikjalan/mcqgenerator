"""
RAG Layer 1 — Data Ingestion
=============================

Public API::

    from app.services.rag.ingestion import IngestionManager

    manager = IngestionManager()
    result  = manager.ingest_file(Path("slides.pptx"))

The module supports PDF, DOC, DOCX, PPT, and PPTX out of the box.
New formats can be added by creating a loader in ``loaders/`` and
decorating it with ``@loader_for(SupportedFormat.XYZ)``.
"""

from app.services.rag.ingestion.manager import IngestionManager  # noqa: F401
from app.services.rag.ingestion.detector import FileTypeDetector  # noqa: F401
from app.services.rag.ingestion.registry import loader_registry  # noqa: F401
from app.services.rag.ingestion.exceptions import (  # noqa: F401
    IngestionError,
    UnsupportedFileTypeError,
    CorruptedFileError,
    EmptyDocumentError,
)

__all__ = [
    "IngestionManager",
    "FileTypeDetector",
    "loader_registry",
    "IngestionError",
    "UnsupportedFileTypeError",
    "CorruptedFileError",
    "EmptyDocumentError",
]
