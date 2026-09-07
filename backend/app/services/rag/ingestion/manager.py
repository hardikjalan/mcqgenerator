"""
manager.py
==========
IngestionManager — the single entry point for Layer 1.

Callers (routes, services) use ``ingest_file`` or ``ingest_bytes`` and
receive a uniform ``IngestionResult`` regardless of the underlying format.

The manager:
1. Detects the file type (``FileTypeDetector``).
2. Looks up the correct loader (``LoaderRegistry``).
3. Builds a ``StandardDocumentMetadata`` template.
4. Delegates to the loader.
5. Wraps the output in an ``IngestionResult``.

Usage::

    from app.services.rag.ingestion import IngestionManager

    manager = IngestionManager()
    result  = manager.ingest_file(Path("/tmp/lecture.pdf"))

    for doc in result.documents:
        print(doc.metadata["file_name"], doc.metadata["page_or_slide_num"])
        print(doc.text[:200])
"""

from __future__ import annotations

import uuid
import tempfile
from pathlib import Path

from app.services.rag.schemas import (
    IngestionResult,
    StandardDocumentMetadata,
    SupportedFormat,
)
from app.services.rag.ingestion.detector import FileTypeDetector
from app.services.rag.ingestion.registry import loader_registry
from app.services.rag.ingestion.exceptions import IngestionError

# Importing the loader modules triggers their @loader_for decorators,
# which registers each loader with the global registry.
import app.services.rag.ingestion.loaders.pdf_loader   # noqa: F401
import app.services.rag.ingestion.loaders.docx_loader  # noqa: F401
import app.services.rag.ingestion.loaders.doc_loader   # noqa: F401
import app.services.rag.ingestion.loaders.pptx_loader  # noqa: F401
import app.services.rag.ingestion.loaders.ppt_loader   # noqa: F401
import app.services.rag.ingestion.loaders.image_loader  # noqa: F401


class IngestionManager:
    """
    Façade for RAG Layer 1 — converts a file into a list of LlamaIndex
    Documents with standardised metadata.
    """

    # ── Public API ────────────────────────────────────────────────────────

    def ingest_file(self, file_path: Path) -> IngestionResult:
        """
        Ingest a file already on disk.

        Parameters
        ----------
        file_path:
            Absolute path to the document.  Must exist and be readable.

        Returns
        -------
        IngestionResult
            Contains the raw LlamaIndex Documents and aggregate stats.

        Raises
        ------
        UnsupportedFileTypeError
            If the file format is not in the registry.
        CorruptedFileError
            If the file cannot be parsed by the registered loader.
        EmptyDocumentError
            If the file parses but yields no text.
        """
        file_path = Path(file_path).resolve()

        if not file_path.exists():
            raise IngestionError(f"File not found: {file_path.name}")

        # 1. Detect format
        fmt: SupportedFormat = FileTypeDetector.detect(file_path)

        # 2. Look up loader
        loader = loader_registry.get(fmt)

        # 3. Build metadata template
        source_id = str(uuid.uuid4())
        metadata = StandardDocumentMetadata(
            file_name=file_path.name,
            file_type=fmt,
            file_size_bytes=file_path.stat().st_size,
            source_id=source_id,
        )

        # 4. Load
        documents = loader.load(file_path, metadata)

        # 5. Build result
        total_chars = sum(len(doc.text) for doc in documents)

        return IngestionResult(
            source_id=source_id,
            file_name=file_path.name,
            file_type=fmt,
            total_units=len(documents),
            documents=documents,
            raw_char_count=total_chars,
        )

    def ingest_bytes(
        self,
        content: bytes,
        file_name: str,
    ) -> IngestionResult:
        """
        Ingest raw bytes (e.g. from a Supabase download or direct upload).

        Writes the bytes to a temporary file, ingests it, and cleans up.

        Parameters
        ----------
        content:
            The raw file content.
        file_name:
            The original filename (used for type detection and metadata).

        Returns
        -------
        IngestionResult
        """
        suffix = Path(file_name).suffix
        with tempfile.NamedTemporaryFile(
            suffix=suffix, delete=False
        ) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        try:
            return self.ingest_file(tmp_path)
        finally:
            # Clean up the temp file.  If removal fails (e.g. the file is
            # still locked on Windows), log it but don't crash.
            try:
                tmp_path.unlink()
            except OSError:
                pass
