"""
RAG Layer 3 — Embeddings
========================

Optional, like OCR. With no key configured ``get_embedder()`` returns None and
extraction still works — files are read and chunked, they just are not indexed
for search.

Public API::

    from app.services.rag.embedding import get_embedder

    embedder = get_embedder()               # None when unconfigured
    vectors = embedder.embed_documents([...])
    query = embedder.embed_query("how do plants make food?")
"""

from app.services.rag.embedding.base import (  # noqa: F401
    Embedder,
    EmbeddingFailedError,
    EmbeddingUnavailableError,
)
from app.services.rag.embedding.gemini import GeminiEmbedder  # noqa: F401

__all__ = [
    "get_embedder",
    "Embedder",
    "GeminiEmbedder",
    "EmbeddingUnavailableError",
    "EmbeddingFailedError",
]


def get_embedder() -> "Embedder | None":
    """Return the configured embedder, or None if there isn't one."""
    from app import config

    if not config.embeddings_enabled():
        return None
    return GeminiEmbedder(
        api_key=config.GEMINI_API_KEY,
        model=config.GEMINI_EMBED_MODEL,
        dimensions=config.EMBED_DIMENSIONS,
    )
