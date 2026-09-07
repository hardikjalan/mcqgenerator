"""
base.py
=======
What a vector store has to do, and the shape of what comes back.

Deliberately three methods. A store that could only ``add`` and ``search``
would leave no way to replace a re-uploaded file, and the alternative — never
deleting — means a corpus that silently accumulates duplicate copies of the
same document, each competing for the same retrieval slots.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from app.services.rag.ingestion.exceptions import IngestionError


class VectorStoreUnavailableError(IngestionError):
    """Raised when no vector store is configured."""

    def __init__(self) -> None:
        super().__init__(
            "Search isn't set up for this deployment, so uploaded files can't "
            "be indexed yet.",
        )


class VectorStoreError(IngestionError):
    """Raised when the store could not be read or written."""

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            "Could not save your files for search just now. Please try again.",
            detail=reason,
        )


@dataclass
class StoredChunk:
    """A chunk on its way into the store."""

    id: str
    source_id: str
    file_name: str
    content: str
    chunk_index: int
    embedding: list[float]
    page_start: int | None = None
    page_end: int | None = None
    owner_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    """A chunk that came back from a search, with how well it matched."""

    id: str
    source_id: str
    file_name: str
    content: str
    score: float
    page_start: int | None = None
    page_end: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def citation(self) -> str:
        """Human-readable origin, e.g. ``lecture.pdf p.3-5``."""
        if self.page_start is None:
            return self.file_name
        if self.page_end and self.page_end != self.page_start:
            return f"{self.file_name} p.{self.page_start}-{self.page_end}"
        return f"{self.file_name} p.{self.page_start}"


@runtime_checkable
class VectorStore(Protocol):
    """Somewhere embedded chunks can be kept and searched."""

    name: str

    def upsert(self, chunks: list[StoredChunk]) -> int:
        """Insert or replace chunks by id. Returns how many were written."""
        ...

    def delete_source(self, source_id: str) -> None:
        """Remove every chunk belonging to one uploaded file."""
        ...

    def search(
        self,
        embedding: list[float],
        *,
        top_k: int,
        min_score: float,
        source_ids: list[str] | None = None,
        owner_id: str | None = None,
    ) -> list[SearchHit]:
        """Return the closest chunks, nearest first.

        ``owner_id`` is not optional in effect: a store shared by several
        faculty members must never return one teacher's material to another,
        and source ids come from the client, so they cannot be the only fence.
        """
        ...
