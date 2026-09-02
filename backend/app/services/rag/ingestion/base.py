"""
base.py
=======
Abstract base class that every document loader must implement.

The contract is intentionally small — a single ``load`` method that takes a
file path and returns a list of LlamaIndex ``Document`` objects with
``StandardDocumentMetadata`` fields merged into each document's metadata dict.

Loaders should raise ``CorruptedFileError`` or ``EmptyDocumentError`` from
``exceptions.py`` rather than letting raw library exceptions bubble up.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from llama_index.core.schema import Document

from app.services.rag.schemas import StandardDocumentMetadata


class BaseLoader(ABC):
    """
    Abstract interface for a single-format document loader.

    Subclasses override ``load`` and call ``_attach_metadata`` on every
    ``Document`` they produce so downstream layers see a uniform schema.
    """

    @abstractmethod
    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        """
        Read *file_path* and return one ``Document`` per logical unit
        (page, slide, section …).

        Parameters
        ----------
        file_path:
            Absolute path to the file on disk (already downloaded from
            Supabase storage or written from an upload).
        metadata:
            Pre-filled metadata template.  The loader must set
            ``page_or_slide_num`` and ``total_pages_or_slides`` on each
            document it emits, and may add keys to ``custom_metadata``.

        Returns
        -------
        list[Document]
            One LlamaIndex Document per page / slide / section, each with
            metadata fields from *metadata* merged into ``doc.metadata``.
        """

    # ── Helpers for subclasses ────────────────────────────────────────────────

    @staticmethod
    def _attach_metadata(doc: Document, meta: StandardDocumentMetadata) -> Document:
        """Merge ``StandardDocumentMetadata`` fields into a Document's
        metadata dict so Layer 2 sees a flat, uniform schema."""
        flat = meta.model_dump()
        # ``ingested_at`` → ISO string so it serialises cleanly.
        flat["ingested_at"] = flat["ingested_at"].isoformat()
        doc.metadata.update(flat)
        return doc
