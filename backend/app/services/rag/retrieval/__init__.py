"""
RAG Layer 3 — Retrieval
=======================

Public API::

    from app.services.rag.retrieval import Retriever

    retriever = Retriever()
    retriever.index(chunks, owner_id=user_id)
    hits = retriever.search("how do plants make food?", source_ids=[...])
"""

from app.services.rag.retrieval.retriever import Retriever  # noqa: F401

__all__ = ["Retriever"]
