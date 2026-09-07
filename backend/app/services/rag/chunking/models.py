"""
models.py
=========
Data contracts, enumerations, and configuration for Layer 3 (Chunking).

Defines:
- ``SemanticType``    — lightweight content classification enum.
- ``ChunkingConfig``  — configurable token sizes & tokenizer settings.
- ``HierarchyContext``— chapter/section/subsection tracking state.
- ``ChunkingResult``  — Layer 3 output contract (parent + child nodes).
- ``count_tokens()``  — flexible token counting with multi-level fallback.
"""

from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Any, Callable

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Semantic type enum ────────────────────────────────────────────────────────

class SemanticType(str, Enum):
    """Lightweight content classification.

    Assigned via best-effort regex matching.  These tags are **metadata
    only** — they never influence chunking boundaries, token sizing,
    retrieval ranking, or text content.
    """

    DEFINITION = "definition"
    CONCEPT = "concept"
    EXPLANATION = "explanation"
    FORMULA = "formula"
    EXAMPLE = "example"
    NUMERICAL = "numerical"
    APPLICATION = "application"
    GENERAL = "general"


# ── Chunking configuration ───────────────────────────────────────────────────

class ChunkingConfig(BaseModel):
    """All tunable knobs for the Layer 3 pipeline.

    Attributes
    ----------
    target_chunk_size : int
        Target child chunk size in tokens (default 512).
    chunk_overlap : int
        Overlap between consecutive children in tokens (default 50).
    max_parent_size : int
        Maximum parent window size in tokens (default 2048).  Oversized
        sections are windowed at semantic boundaries.
    tokenizer_fn : Callable[[str], int] | None
        Optional user-supplied function that returns a token count for a
        string.  When ``None``, the resolver falls through to the
        project's existing tokenizer, tiktoken (if installed), or a
        character-ratio heuristic.
    fallback_chars_per_token : float
        Heuristic ratio used when no external tokenizer is available.
    """

    target_chunk_size: int = 512
    chunk_overlap: int = 50
    max_parent_size: int = 2048
    tokenizer_fn: Callable[[str], int] | None = None
    fallback_chars_per_token: float = 4.0

    class Config:
        arbitrary_types_allowed = True


# ── Token counting with multi-level fallback ─────────────────────────────────

_resolved_counter: Callable[[str], int] | None = None


def _resolve_token_counter(config: ChunkingConfig) -> Callable[[str], int]:
    """Resolve a token counter once and cache it for the process lifetime.

    Resolution order:
    1. ``config.tokenizer_fn`` (user-supplied).
    2. ``llama_index.core.Settings.tokenizer`` (project-wide tokenizer).
    3. ``tiktoken.get_encoding("cl100k_base")`` (if installed).
    4. Character-ratio heuristic.
    """
    global _resolved_counter

    # 1. Explicit user callable — always wins.
    if config.tokenizer_fn is not None:
        return config.tokenizer_fn

    # Return cached resolver when available (skip re-probing on every call).
    if _resolved_counter is not None:
        return _resolved_counter

    # 2. LlamaIndex project tokenizer.
    try:
        from llama_index.core import Settings  # noqa: WPS433

        if Settings.tokenizer is not None:
            tok = Settings.tokenizer

            def _llama_counter(text: str) -> int:
                return len(tok(text))

            _resolved_counter = _llama_counter
            logger.debug("Token counter: llama_index.core.Settings.tokenizer")
            return _resolved_counter
    except Exception:  # noqa: BLE001
        pass

    # 3. tiktoken (if installed).
    try:
        import tiktoken  # noqa: WPS433

        enc = tiktoken.get_encoding("cl100k_base")

        def _tiktoken_counter(text: str) -> int:
            return len(enc.encode(text))

        _resolved_counter = _tiktoken_counter
        logger.debug("Token counter: tiktoken (cl100k_base)")
        return _resolved_counter
    except Exception:  # noqa: BLE001
        pass

    # 4. Heuristic fallback.
    ratio = config.fallback_chars_per_token

    def _heuristic_counter(text: str) -> int:
        return max(1, int(len(text) / ratio))

    _resolved_counter = _heuristic_counter
    logger.debug("Token counter: heuristic (%.1f chars/token)", ratio)
    return _resolved_counter


def count_tokens(text: str, config: ChunkingConfig) -> int:
    """Return the token count for *text* using the best available counter."""
    counter = _resolve_token_counter(config)
    return counter(text)


# ── Hierarchy context ─────────────────────────────────────────────────────────

class HierarchyContext(BaseModel):
    """Tracks the active heading hierarchy for a chunk.

    ``level`` is the relative depth (1, 2, 3 …) inferred from Markdown
    heading markers.  ``chapter``, ``section``, and ``subsection`` are
    populated **only** when explicit numbering or keywords confirm them.
    """

    level: int = 0
    heading: str | None = None
    chapter: str | None = None
    section: str | None = None
    subsection: str | None = None
    path: list[str] = Field(default_factory=list)

    def to_header_path(self) -> str:
        """Return a human-readable hierarchy breadcrumb string."""
        if self.chapter or self.section:
            parts = [p for p in (self.chapter, self.section, self.subsection) if p]
            return " > ".join(parts)
        return " > ".join(self.path) if self.path else (self.heading or "")


# ── Layer 3 output contract ──────────────────────────────────────────────────

class ChunkingResult(BaseModel):
    """Complete output of Layer 3 for a single document (``source_id``).

    ``parent_chunks`` and ``child_chunks`` are lists of LlamaIndex
    ``TextNode`` objects typed as ``Any`` because Pydantic cannot natively
    serialise them.
    """

    source_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_name: str = ""
    file_type: str = ""
    parent_chunks: list[Any] = Field(default_factory=list)
    child_chunks: list[Any] = Field(default_factory=list)
    total_parents: int = 0
    total_children: int = 0
    errors: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True
