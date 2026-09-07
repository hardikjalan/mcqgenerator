"""
retriever.py
============
RAG Layer 3 — putting chunks into the index and getting them back out.

This is the join between the embedder and the store. Neither knows about the
other: the embedder turns text into vectors, the store keeps vectors and
compares them, and this module is what decides when each happens.

Indexing is **best-effort by design**. If embeddings or the store are not
configured — or the embedding API is having a bad minute — a file that was
read successfully is still a file that was read successfully. Failing the
whole upload because the search index could not be updated would throw away
work the user already waited for. The failure is reported per file instead.

Searching is not best-effort. A search that quietly returns nothing looks
identical to a search that found nothing, and the second is a legitimate
answer while the first is a bug.
"""

from __future__ import annotations

from typing import Any

from app import config
from app.services.rag.embedding import get_embedder
from app.services.rag.embedding.base import Embedder, EmbeddingUnavailableError
from app.services.rag.store import get_store
from app.services.rag.store.base import (
    SearchHit,
    StoredChunk,
    VectorStore,
    VectorStoreUnavailableError,
)


class Retriever:
    """Indexes chunks and searches them."""

    def __init__(
        self,
        *,
        embedder: Embedder | None = None,
        store: VectorStore | None = None,
    ) -> None:
        # Resolved once per instance, but instances are created per request —
        # so a key added to the environment takes effect without a restart.
        self._embedder = embedder if embedder is not None else get_embedder()
        self._store = store if store is not None else get_store()

    @property
    def available(self) -> bool:
        """True when both halves are configured."""
        return self._embedder is not None and self._store is not None

    # ── Indexing ──────────────────────────────────────────────────────────

    def index(self, chunks: list[Any], *, owner_id: str | None = None) -> int:
        """Embed *chunks* and write them to the store.

        Returns how many were indexed. Raises if unavailable or if the store
        rejects the write — the caller decides whether that is fatal.
        """
        if not chunks:
            return 0
        if self._embedder is None:
            raise EmbeddingUnavailableError()
        if self._store is None:
            raise VectorStoreUnavailableError()

        vectors = self._embedder.embed_documents([chunk.text for chunk in chunks])

        # An embedder that returns a different number of vectors than it was
        # given would silently pair chunks with the wrong embeddings, and the
        # result is a search index that returns confidently wrong passages.
        if len(vectors) != len(chunks):
            raise ValueError(
                f"embedder returned {len(vectors)} vectors for {len(chunks)} chunks"
            )

        # Replacing the source first means a re-upload with fewer chunks does
        # not leave the extra ones from last time behind. Deterministic ids
        # cover overwriting; only shrinking needs the delete.
        source_id = str(chunks[0].metadata.get("source_id", ""))
        if source_id:
            self._store.delete_source(source_id)

        return self._store.upsert([
            _to_stored(chunk, vector, owner_id)
            for chunk, vector in zip(chunks, vectors)
        ])

    # ── Searching ─────────────────────────────────────────────────────────

    def search(
        self,
        question: str,
        *,
        source_ids: list[str] | None = None,
        owner_id: str | None = None,
        top_k: int | None = None,
        min_score: float | None = None,
    ) -> list[SearchHit]:
        """Find the chunks most likely to answer *question*.

        Two scopes, doing different jobs. ``source_ids`` narrows the search to
        the files this quiz is being built from — a usefulness filter, and it
        comes from the client. ``owner_id`` is the security one: it comes from
        a verified token and keeps one faculty member out of another's
        material regardless of what ids they send.
        """
        if self._embedder is None:
            raise EmbeddingUnavailableError()
        if self._store is None:
            raise VectorStoreUnavailableError()

        return self._store.search(
            self._embedder.embed_query(question),
            top_k=top_k or config.RETRIEVAL_TOP_K,
            min_score=min_score if min_score is not None else config.RETRIEVAL_MIN_SCORE,
            source_ids=source_ids,
            owner_id=owner_id,
        )


# ── Mapping ───────────────────────────────────────────────────────────────────

def _to_stored(chunk: Any, vector: list[float], owner_id: str | None) -> StoredChunk:
    meta = dict(chunk.metadata)
    return StoredChunk(
        id=chunk.id_,
        source_id=str(meta.get("source_id", "")),
        file_name=str(meta.get("file_name", "")),
        content=chunk.text,
        chunk_index=int(meta.get("chunk_index", 0)),
        embedding=vector,
        page_start=meta.get("page_start"),
        page_end=meta.get("page_end"),
        owner_id=owner_id,
        metadata=meta,
    )
