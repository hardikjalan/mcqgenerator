"""
models.py
=========
Data models and configurations for Layer 5: Retrieval.
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class RetrievalConfig(BaseModel):
    """Configuration options for Layer 5 vector retrieval."""

    top_k: int = 5
    table_name: str = "document_chunks"
    rpc_name: str = "match_document_chunks"


class RetrievalQuery(BaseModel):
    """Encapsulates teacher input parameters selected for retrieval.

    Filters out generation-only fields (gradeLevel, questionCount, timeLimit)
    and retains primary (topicsCovered, learningObjective) and supporting
    (subjectName, questionType) inputs.
    """

    subject_name: str
    topics_covered: str
    learning_objective: str
    question_type: str | None = None
    source_ids: list[str] = Field(default_factory=list)

    def to_semantic_query(self) -> str:
        """Construct a concise, natural semantic search query."""
        parts: list[str] = []

        if self.topics_covered.strip():
            parts.append(f"Topics: {self.topics_covered.strip()}")

        if self.learning_objective.strip():
            parts.append(f"Learning Objective: {self.learning_objective.strip()}")

        if self.subject_name.strip():
            parts.append(f"Subject: {self.subject_name.strip()}")

        # Secondary contextual signal: only add if helpful, omit for 'all'
        qtype = (self.question_type or "").strip().lower()
        if qtype and qtype != "all":
            if qtype == "truefalse":
                parts.append("Format context: factual verification")
            elif qtype in ("single", "multiple"):
                parts.append(f"Format context: {qtype} choice assessment")

        return "\n".join(parts)


class RetrievedChildChunk(BaseModel):
    """Represents a matched child chunk from Supabase vector search."""

    node_id: str
    parent_id: str | None = None
    source_id: str
    content: str
    similarity: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def file_name(self) -> str:
        return self.metadata.get("file_name", "")

    @property
    def page_or_slide_num(self) -> int | None:
        return self.metadata.get("page_or_slide_num")

    @property
    def page_numbers(self) -> list[int]:
        return self.metadata.get("page_numbers", [])

    @property
    def semantic_type(self) -> str | None:
        return self.metadata.get("semantic_type")

    @property
    def hierarchy_level(self) -> int:
        return self.metadata.get("hierarchy_level", 0)

    @property
    def heading(self) -> str | None:
        return self.metadata.get("heading")


class RetrievedParentContext(BaseModel):
    """Represents a parent chunk providing broader context for question generation.

    Includes deduplicated parent content, maximum similarity score among
    its matching children, and child-level provenance for exact traceability.
    """

    parent_id: str
    source_id: str
    content: str
    similarity: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    matched_children: list[RetrievedChildChunk] = Field(default_factory=list)

    @property
    def file_name(self) -> str:
        return self.metadata.get("file_name", "")

    @property
    def page_or_slide_num(self) -> int | None:
        return self.metadata.get("page_or_slide_num")

    @property
    def page_numbers(self) -> list[int]:
        return self.metadata.get("page_numbers", [])

    @property
    def heading(self) -> str | None:
        return self.metadata.get("heading")

    @property
    def chapter(self) -> str | None:
        return self.metadata.get("chapter")

    @property
    def section(self) -> str | None:
        return self.metadata.get("section")

    @property
    def subsection(self) -> str | None:
        return self.metadata.get("subsection")

    @property
    def hierarchy_level(self) -> int:
        return self.metadata.get("hierarchy_level", 0)

    @property
    def semantic_type(self) -> str | None:
        if "semantic_type" in self.metadata:
            return self.metadata["semantic_type"]
        if self.matched_children:
            best_child = max(self.matched_children, key=lambda c: c.similarity)
            return best_child.semantic_type
        return None


class RetrievalResult(BaseModel):
    """Complete output contract for Layer 5 (Retrieval) to Layer 6."""

    query: str
    source_ids: list[str] = Field(default_factory=list)
    retrieved_contexts: list[RetrievedParentContext] = Field(default_factory=list)
    total_children_matched: int = 0
    total_parents_returned: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return len(self.errors) == 0 and len(self.retrieved_contexts) > 0
