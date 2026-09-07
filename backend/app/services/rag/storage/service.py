"""
service.py
==========
Orchestrator for Layer 4: VectorStorageManager.
"""

from __future__ import annotations

import logging
from typing import Any

from supabase import Client, create_client
from llama_index.core.schema import TextNode

from app.services.rag.chunking.models import ChunkingResult
from app.services.rag.storage.models import StorageConfig, StorageResult
from app.services.rag.storage.embedder import Embedder

logger = logging.getLogger(__name__)


class VectorStorageManager:
    """Manages embedding generation and Supabase storage for Layer 3 chunks."""

    def __init__(
        self,
        supabase_client: Client,
        config: StorageConfig | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.supabase = supabase_client
        self.config = config or StorageConfig()
        self.embedder = embedder or Embedder(config=self.config)

    def store_chunks(self, chunking_result: ChunkingResult) -> StorageResult:
        """Embed and store the child chunks from a ChunkingResult.

        Parameters
        ----------
        chunking_result : ChunkingResult
            The output from Layer 3, containing parent and child TextNodes.

        Returns
        -------
        StorageResult
        """
        source_id = chunking_result.source_id
        children = chunking_result.child_chunks

        if not children:
            return StorageResult(source_id=source_id, chunks_inserted=0)

        result = StorageResult(source_id=source_id)

        # 1. Extract text
        texts = [child.text for child in children]

        # 2. Generate embeddings
        try:
            embeddings = self.embedder.generate_embeddings(texts)
        except Exception as e:
            result.errors.append(f"Embedding generation failed: {e}")
            return result

        if len(embeddings) != len(children):
            result.errors.append("Mismatch between number of chunks and generated embeddings.")
            return result

        # 3. Map to Supabase rows
        rows: list[dict[str, Any]] = []

        # 3a. Parents (stored with embedding=None for simple parent-context lookup in Layer 5)
        parents = chunking_result.parent_chunks or []
        for parent in parents:
            rows.append({
                "node_id": parent.node_id,
                "parent_id": None,
                "source_id": source_id,
                "content": parent.text,
                "embedding": None,
                "metadata": parent.metadata,
            })

        # 3b. Children (stored with embeddings for vector similarity search)
        for child, embedding in zip(children, embeddings):
            meta = child.metadata

            # LlamaIndex stores parent relationships in .relationships or we can extract from metadata
            parent_id = meta.get("parent_id")

            row = {
                "node_id": child.node_id,
                "parent_id": parent_id,
                "source_id": source_id,
                "content": child.text,
                "embedding": embedding,
                "metadata": meta,
            }
            rows.append(row)

        # 4. Upsert into Supabase
        table_name = self.config.table_name
        try:
            # We use upsert on node_id so re-processing a document safely updates existing chunks.
            response = self.supabase.table(table_name).upsert(rows, on_conflict="node_id").execute()
            result.chunks_inserted = len(response.data or [])
        except Exception as e:
            logger.error("Supabase upsert failed for source_id=%s: %s", source_id, e)
            result.errors.append(f"Database insertion failed: {e}")

        return result
