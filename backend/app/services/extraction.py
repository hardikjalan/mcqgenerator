"""
extraction.py
=============
Turns the dashboard's list of uploaded files into extracted text.

This is the seam between the API and the RAG pipeline. ``routes.py`` knows
about HTTP and knows nothing about ingestion; the ``rag`` package knows about
ingestion and nothing about HTTP. This module is the only thing that knows
both — it takes plain values in and returns plain values out, and imports no
FastAPI.

The governing rule here is **per-file isolation**. A faculty member uploading
five files and getting one blanket error, with no indication of which file was
the problem, would have to bisect by hand. So every file is attempted
independently and every outcome — success or failure — comes back with that
file's name attached.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app import config
from app.services.rag.ingestion import IngestionManager
from app.services.rag.ingestion.exceptions import IngestionError
from app.services.rag.ingestion.fetcher import download
from app.services.rag.ingestion.ocr import OCRUnavailableError
from app.services.rag.processing.chunking import DocumentChunker
from app.services.rag.retrieval import Retriever

# Re-exported so callers and tests have one name to reach for. The values live
# in app/config.py, which is the only place a limit is written down.
MAX_FILE_BYTES = config.MAX_FILE_BYTES
MAX_CUMULATIVE_BYTES = config.MAX_CUMULATIVE_BYTES

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"})


@dataclass(frozen=True)
class SourceInput:
    """One file the dashboard wants extracted."""

    name: str
    signed_url: str
    size_bytes: int


@dataclass
class ExtractedSource:
    """
    The outcome of extracting one file.

    ``documents`` holds the whole-page Documents and ``chunks`` the
    retrieval-sized pieces cut from them. Neither is part of the API response
    — the browser only ever displayed counts, and the text is needed
    server-side, which is where the vector store will read it from.
    """

    name: str
    ok: bool
    chars: int = 0
    error: str | None = None
    source_id: str | None = None
    indexed: bool = False
    index_note: str | None = None
    documents: list[Any] | None = None
    chunks: list[Any] | None = None


def extract_sources(
    sources: list[SourceInput],
    *,
    manager: IngestionManager | None = None,
    chunker: DocumentChunker | None = None,
    retriever: Retriever | None = None,
    owner_id: str | None = None,
) -> list[ExtractedSource]:
    """
    Download and extract every file in *sources*.

    Never raises for a per-file problem — a failure becomes an
    ``ExtractedSource`` with ``ok=False`` and a user-safe ``error``. The list
    comes back in the order it was given so the dashboard can match rows to
    the files it displayed.

    Parameters
    ----------
    sources:
        Files to process, each with a signed download URL.
    manager:
        Injectable for tests. Defaults to a fresh ``IngestionManager``.
    chunker:
        Injectable for tests. Defaults to a fresh ``DocumentChunker``.
    retriever:
        Injectable for tests. Defaults to a fresh ``Retriever``.
    owner_id:
        Recorded on every indexed chunk. Optional today because the API has no
        authenticated user yet; see the note in routes.py.
    """
    manager = manager or IngestionManager()
    chunker = chunker or DocumentChunker()
    retriever = retriever if retriever is not None else Retriever()
    results: list[ExtractedSource] = []
    budget = config.MAX_CUMULATIVE_BYTES

    for source in sources:
        # Short-circuit before the download: with OCR switched off an image
        # can only fail, and paying for the transfer first to reach the same
        # answer helps nobody. With OCR on it falls through to the normal
        # path, where the image loader handles it.
        if _is_image(source.name) and not config.ocr_enabled():
            results.append(
                ExtractedSource(source.name, ok=False, error=OCRUnavailableError().message)
            )
            continue

        if budget <= 0:
            results.append(
                ExtractedSource(
                    source.name,
                    ok=False,
                    error="Skipped — the combined size of your files exceeds the limit.",
                )
            )
            continue

        results.append(_extract_one(source, manager, chunker, retriever, owner_id, budget))

        # Charge the budget with what actually arrived, not what the request
        # claimed. A failed download costs nothing.
        last = results[-1]
        if last.ok:
            budget -= min(source.size_bytes, config.MAX_FILE_BYTES)

    return results


# ── Internal ──────────────────────────────────────────────────────────────────

def _extract_one(
    source: SourceInput,
    manager: IngestionManager,
    chunker: DocumentChunker,
    retriever: Retriever,
    owner_id: str | None,
    budget: int,
) -> ExtractedSource:
    """Download and ingest a single file, converting any failure into a row."""
    try:
        content = download(
            source.signed_url,
            file_name=source.name,
            max_bytes=min(config.MAX_FILE_BYTES, budget),
        )
        result = manager.ingest_bytes(content, source.name)

    except IngestionError as exc:
        # Covers download, detection, parsing and emptiness failures — every
        # one of them already carries a message written to be shown as-is.
        if exc.detail:
            print(f"[extraction] {source.name}: {exc.detail}")
        return ExtractedSource(source.name, ok=False, error=exc.message)

    except Exception as exc:  # noqa: BLE001 - last line of defence
        # An unexpected failure must not take down the other files in the
        # batch. Log the real cause, show the user a sentence.
        print(f"[extraction] {source.name}: unexpected {type(exc).__name__}: {exc}")
        return ExtractedSource(
            source.name,
            ok=False,
            error=f"Something went wrong reading {source.name}. Try re-saving it as a PDF.",
        )

    # Chunking is cheap and pure — no network, no model — so it runs inline
    # with extraction rather than being deferred. Doing it here means the
    # response can report a chunk count, which is the first signal a faculty
    # member gets that their upload is actually usable.
    chunks = chunker.chunk_documents(result.documents)

    # Indexing is best-effort. The file has already been downloaded, parsed
    # and chunked by this point; failing the whole upload because the search
    # index could not be written would throw that away and tell the user their
    # file was bad, which is not what happened. The reason is reported instead.
    indexed, note = _index(chunks, retriever, owner_id, source.name)

    return ExtractedSource(
        source.name,
        ok=True,
        chars=result.raw_char_count,
        source_id=result.source_id,
        indexed=indexed,
        index_note=note,
        documents=result.documents,
        chunks=chunks,
    )


def _index(
    chunks: list[Any],
    retriever: Retriever,
    owner_id: str | None,
    file_name: str,
) -> tuple[bool, str | None]:
    """Try to index *chunks*, returning (indexed, note-if-not)."""
    if not retriever.available:
        return False, "Search isn't configured, so this file was read but not indexed."

    try:
        retriever.index(chunks, owner_id=owner_id)
    except IngestionError as exc:
        if exc.detail:
            print(f"[indexing] {file_name}: {exc.detail}")
        return False, exc.message
    except Exception as exc:  # noqa: BLE001
        print(f"[indexing] {file_name}: unexpected {type(exc).__name__}: {exc}")
        return False, "This file was read but could not be saved for search."

    return True, None


def _is_image(file_name: str) -> bool:
    return Path(file_name).suffix.lower() in _IMAGE_EXTENSIONS
