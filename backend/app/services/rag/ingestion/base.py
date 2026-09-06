"""
base.py
=======
Abstract base class that every document loader must implement.

The contract is intentionally small — a single ``load`` method that takes a
file path and returns a list of LlamaIndex ``Document`` objects with
``StandardDocumentMetadata`` fields merged into each document's metadata dict.

Loaders should raise ``CorruptedFileError`` or ``EmptyDocumentError`` from
``exceptions.py`` rather than letting raw library exceptions bubble up.

After extraction and metadata attachment, loaders call
``clean_and_validate()`` which routes documents through the centralised
``DocumentCleaner`` and raises ``EmptyDocumentError`` if all cleaned
content is blank.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from llama_index.core.schema import Document

from app.services.rag.schemas import StandardDocumentMetadata
from app.services.rag.processing.cleaning import DocumentCleaner
from app.services.rag.ingestion.exceptions import EmptyDocumentError


class BaseLoader(ABC):
    """
    Abstract interface for a single-format document loader.

    Subclasses override ``load`` and call ``_attach_metadata`` on every
    ``Document`` they produce so downstream layers see a uniform schema.
    After building the raw Documents, call ``clean_and_validate`` to run
    the centralised cleaning pipeline and validate non-emptiness.
    """

    def __init__(self, cleaner: DocumentCleaner | None = None) -> None:
        self.cleaner = cleaner or DocumentCleaner()

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

    def clean_and_validate(
        self,
        docs: list[Document],
        file_name: str,
    ) -> list[Document]:
        """Run ``DocumentCleaner`` on *docs* and raise if nothing remains.

        This is the single place where post-clean emptiness is checked,
        ensuring uniform behaviour across all loaders.

        Parameters
        ----------
        docs:
            Raw Documents with text and metadata already attached.
        file_name:
            Used in the ``EmptyDocumentError`` message.

        Returns
        -------
        list[Document]
            The same list of Documents with cleaned ``.text``.

        Raises
        ------
        EmptyDocumentError
            If no document contains non-whitespace text after cleaning.
        """
        cleaned = self.cleaner.clean_documents(docs)
        if not cleaned or not any(d.text.strip() for d in cleaned):
            raise EmptyDocumentError(file_name)
        return cleaned
