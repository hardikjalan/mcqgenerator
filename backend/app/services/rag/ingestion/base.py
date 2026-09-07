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


# ── Metadata hygiene ──────────────────────────────────────────────────────────
# LlamaIndex readers attach their own keys to doc.metadata. Some are actively
# harmful downstream, so they are dropped before the document leaves Layer 1.
_READER_NOISE_KEYS = frozenset({
    "file_path",           # absolute path of the *temp* file — leaks the server
                           # filesystem and is meaningless once ingestion ends
    "text_sections",       # PptxReader: duplicates doc.text in full, doubling
                           # memory and embedding cost for zero added signal
    "page_label",          # duplicate of page_or_slide_num
    "images", "charts", "tables",         # reader-internal structures; unbounded
    "extraction_errors", "extraction_warnings",
})

# Keys the *embedding* model should never see. Metadata is prepended to node
# text by default, so without this every chunk's vector is polluted by a UUID,
# a timestamp and a byte count — noise that pushes semantically similar chunks
# apart. Kept out of the embedding, still available for filtering and display.
_EXCLUDE_FROM_EMBEDDING = (
    "file_type", "file_size_bytes", "source_id", "ingested_at",
    "total_pages_or_slides",
)

# Keys the LLM should not see at generation time. file_name and
# page_or_slide_num are deliberately absent — the model needs them to say
# which slide a question came from.
_EXCLUDE_FROM_LLM = (
    "file_size_bytes", "source_id", "ingested_at",
)

# Loader- and reader-supplied extras are flattened onto the top level under
# this prefix. They used to sit in a nested ``custom_metadata`` dict, which
# LlamaIndex accepts but most vector stores do not — Chroma, Pinecone and
# pgvector all require metadata values to be scalars, so the nested dict would
# have failed at insert time in Layer 3 rather than here.
_CUSTOM_PREFIX = "x_"


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
        """Merge ``StandardDocumentMetadata`` into a Document's metadata dict.

        Three things happen here, in order:

        1. Reader-added noise keys are dropped (see ``_READER_NOISE_KEYS``).
           Anything else the reader supplied is folded into
           ``custom_metadata`` rather than left loose at the top level, so
           the top level is exactly the standard schema and nothing else.
        2. The standard fields are written, with ``ingested_at`` as an ISO
           string so it serialises cleanly.
        3. The embedding and LLM exclusion lists are set, so bookkeeping
           fields never reach a vector or a prompt.
        """
        flat = meta.model_dump()

        # Reader extras that duplicate a standard field are dropped too —
        # keeping both would mean the same value under two different names.
        reader_extras = {
            key: value
            for key, value in doc.metadata.items()
            if key not in _READER_NOISE_KEYS
            and key not in flat
            and value not in (None, "", [], {})
        }

        flat["ingested_at"] = flat["ingested_at"].isoformat()
        # Loader-supplied custom_metadata wins over reader extras on a clash.
        extras = {**reader_extras, **flat.pop("custom_metadata", {})}

        doc.metadata.clear()
        doc.metadata.update(flat)
        for key, value in extras.items():
            doc.metadata[f"{_CUSTOM_PREFIX}{key}"] = _as_scalar(value)

        custom_keys = [f"{_CUSTOM_PREFIX}{key}" for key in extras]
        doc.excluded_embed_metadata_keys = list(_EXCLUDE_FROM_EMBEDDING) + custom_keys
        doc.excluded_llm_metadata_keys = list(_EXCLUDE_FROM_LLM) + custom_keys
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


def _as_scalar(value: object) -> str | int | float | bool | None:
    """Coerce a metadata value to something a vector store will accept."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)
