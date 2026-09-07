"""
base.py
=======
The embedding contract.

An **embedding** is a list of numbers describing what a piece of text means.
Two chunks about photosynthesis land near each other; a chunk about mitosis
lands far away. Searching is then a distance calculation rather than a keyword
match, which is why "how do plants make food" can find a paragraph that never
uses those words.

Two methods, not one, because the two sides of a search are not the same job.
Providers offer a task-type hint — a document is embedded to be *found*, a
question to *find* — and using it lifts retrieval quality for free. A single
``embed()`` method would have thrown that away.

The rule that matters more than any of this: **documents and queries must be
embedded by the same model, with the same dimensions**. Vectors from different
models are not comparable, so switching model after indexing silently returns
nonsense rather than failing. That is why the dimension is a deliberate
setting in config rather than a model default.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.services.rag.ingestion.exceptions import IngestionError


class EmbeddingUnavailableError(IngestionError):
    """Raised when no embedding provider is configured."""

    def __init__(self) -> None:
        super().__init__(
            "Search isn't switched on for this deployment, so uploaded files "
            "can't be indexed yet.",
        )


class EmbeddingFailedError(IngestionError):
    """Raised when a provider could not embed the text."""

    def __init__(self, reason: str = "") -> None:
        super().__init__(
            "Could not index your files just now. Please try again in a moment.",
            detail=reason,
        )


@runtime_checkable
class Embedder(Protocol):
    """Anything that can turn text into vectors."""

    name: str
    dimensions: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed chunks for storage. Returns one vector per input, in order."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Embed a search query."""
        ...
