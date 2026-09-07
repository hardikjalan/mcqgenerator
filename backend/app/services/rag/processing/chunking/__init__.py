"""
chunking — RAG Layer 2
======================

Public API::

    from app.services.rag.processing.chunking import DocumentChunker

    chunks = DocumentChunker().chunk_documents(ingestion_result.documents)

Chunks come back as LlamaIndex ``TextNode`` objects, which is what every
LlamaIndex vector store accepts — so Layer 3 can index them without a
conversion step.
"""

from app.services.rag.processing.chunking.chunker import DocumentChunker  # noqa: F401

__all__ = ["DocumentChunker"]
