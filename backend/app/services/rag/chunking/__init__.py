"""
RAG Layer 3 — Chunking
=======================

Provides Hierarchical + Semantic + Parent-Child chunking of cleaned
LlamaIndex ``Document`` objects.

Public API:
    ``ChunkingManager``   — the pipeline coordinator.
    ``ChunkingConfig``    — configurable token sizes & tokenizer.
    ``ChunkingResult``    — output contract (parent + child nodes).
    ``SemanticType``      — best-effort content classification enum.
"""

from app.services.rag.chunking.models import (  # noqa: F401
    ChunkingConfig,
    ChunkingResult,
    HierarchyContext,
    SemanticType,
)
from app.services.rag.chunking.manager import ChunkingManager  # noqa: F401

__all__ = [
    "ChunkingConfig",
    "ChunkingManager",
    "ChunkingResult",
    "HierarchyContext",
    "SemanticType",
]
