"""
RAG Layer 4 — Embedding & Storage
=================================

Provides embedding generation using OpenAI and robust vector storage 
in Supabase using pgvector for Layer 3 chunks.

Public API:
    ``VectorStorageManager`` — orchestrates embedding and storage.
    ``StorageConfig``        — configures model and table settings.
    ``StorageResult``        — summary of operation outcomes.
"""

from app.services.rag.storage.models import StorageConfig, StorageResult
from app.services.rag.storage.service import VectorStorageManager

__all__ = [
    "StorageConfig",
    "StorageResult",
    "VectorStorageManager",
]
