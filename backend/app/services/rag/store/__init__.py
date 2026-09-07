"""
RAG Layer 3 — Vector store
==========================

Optional, like OCR and embeddings. ``get_store()`` returns None when Supabase
credentials are absent, and extraction still works — files are read and
chunked, they just are not saved for search.

Public API::

    from app.services.rag.store import get_store

    store = get_store()                    # None when unconfigured
    store.upsert(chunks)
    hits = store.search(query_vector, top_k=8, min_score=0.35)
"""

from app.services.rag.store.base import (  # noqa: F401
    SearchHit,
    StoredChunk,
    VectorStore,
    VectorStoreError,
    VectorStoreUnavailableError,
)
from app.services.rag.store.pgvector import SupabaseVectorStore  # noqa: F401

__all__ = [
    "get_store",
    "SearchHit",
    "StoredChunk",
    "VectorStore",
    "SupabaseVectorStore",
    "VectorStoreError",
    "VectorStoreUnavailableError",
]


def get_store() -> "VectorStore | None":
    """Return the configured vector store, or None if there isn't one."""
    from app import config

    if not config.vector_store_enabled():
        return None
    return SupabaseVectorStore(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY)
