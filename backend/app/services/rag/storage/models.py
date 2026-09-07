"""
models.py
=========
Data contracts and configuration for Layer 4 (Storage).
"""

from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class StorageConfig(BaseModel):
    """Configuration for embedding and Supabase storage."""

    # Embedding settings
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    embedding_batch_size: int = 100

    # Supabase settings
    table_name: str = "document_chunks"

    class Config:
        arbitrary_types_allowed = True


class StorageResult(BaseModel):
    """Summary of the embedding and insertion operation."""

    source_id: str
    chunks_inserted: int = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def is_success(self) -> bool:
        return len(self.errors) == 0
