"""
service.py
==========
Orchestrator for Layer 5: RetrievalManager.
Coordinates query building, embedding generation, Supabase pgvector
similarity search, and parent-context resolution with document isolation.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from supabase import Client

from app.services.rag.storage.embedder import Embedder
from app.services.rag.storage.models import StorageConfig
from app.services.rag.retrieval.models import (
    RetrievalConfig,
    RetrievalQuery,
    RetrievalResult,
    RetrievedChildChunk,
    RetrievedParentContext,
)

logger = logging.getLogger(__name__)


class RetrievalManager:
    """Manages semantic retrieval of child chunks and resolution of parent context."""

    def __init__(
        self,
        supabase_client: Client,
        config: RetrievalConfig | None = None,
        embedder: Embedder | None = None,
    ) -> None:
        self.supabase = supabase_client
        self.config = config or RetrievalConfig()
        # Reuse Layer 4 embedder (text-embedding-3-small, 1536 dim)
        self.embedder = embedder or Embedder(config=StorageConfig())

    @staticmethod
    def build_query(
        subject_name: str,
        topics_covered: str,
        learning_objective: str,
        source_ids: list[str],
        question_type: str | None = None,
    ) -> RetrievalQuery:
        """Create a validated RetrievalQuery from teacher input fields."""
        return RetrievalQuery(
            subject_name=subject_name,
            topics_covered=topics_covered,
            learning_objective=learning_objective,
            question_type=question_type,
            source_ids=source_ids,
        )

    def retrieve(self, query: RetrievalQuery) -> RetrievalResult:
        """Execute semantic retrieval against Supabase pgvector.

        Steps:
        1. Validate source_ids for strict document isolation.
        2. Format concise semantic query and generate embedding.
        3. Execute Supabase RPC (match_document_chunks) to retrieve Top-K child chunks.
        4. Deduplicate parent_ids and batch fetch parent chunks.
        5. Group matched children under their respective parents and preserve provenance.
        """
        source_ids = [sid for sid in query.source_ids if sid]
        semantic_query_text = query.to_semantic_query()

        result = RetrievalResult(
            query=semantic_query_text,
            source_ids=source_ids,
        )

        # 1. Source isolation guard
        if not source_ids:
            result.errors.append("At least one valid source_id is required for document isolation.")
            return result

        if not semantic_query_text.strip():
            result.errors.append("Search query is empty. Subject, topics, or objective required.")
            return result

        # 2. Embedding generation
        try:
            embeddings = self.embedder.generate_embeddings([semantic_query_text])
            if not embeddings or len(embeddings[0]) != 1536:
                result.errors.append("Failed to produce valid 1536-dimensional query embedding.")
                return result
            query_embedding = embeddings[0]
        except Exception as exc:
            logger.error("Embedding generation failed for retrieval: %s", exc)
            result.errors.append(f"Query embedding generation failed: {exc}")
            return result

        # 3. Supabase RPC execution
        try:
            rpc_params = {
                "query_embedding": query_embedding,
                "match_count": self.config.top_k,
                "filter_source_ids": source_ids,
            }
            response = self.supabase.rpc(self.config.rpc_name, rpc_params).execute()
            rows: list[dict[str, Any]] = response.data or []
        except Exception as exc:
            logger.error("Supabase vector search RPC failed: %s", exc)
            result.errors.append(f"Vector search failed: {exc}")
            return result

        if not rows:
            logger.info("No matching chunks found for source_ids=%s", source_ids)
            return result

        # 4. Parse retrieved child chunks
        child_chunks: list[RetrievedChildChunk] = []
        for r in rows:
            child = RetrievedChildChunk(
                node_id=r["node_id"],
                parent_id=r.get("parent_id"),
                source_id=r["source_id"],
                content=r["content"],
                similarity=float(r.get("similarity", 0.0)),
                metadata=r.get("metadata") or {},
            )
            child_chunks.append(child)

        result.total_children_matched = len(child_chunks)

        # 5. Group children by parent_id
        parent_to_children: dict[str, list[RetrievedChildChunk]] = defaultdict(list)
        unparented_children: list[RetrievedChildChunk] = []

        for child in child_chunks:
            if child.parent_id:
                parent_to_children[child.parent_id].append(child)
            else:
                unparented_children.append(child)

        # 6. Batch fetch parent rows from Supabase
        unique_parent_ids = list(parent_to_children.keys())
        parent_rows_by_id: dict[str, dict[str, Any]] = {}

        if unique_parent_ids:
            try:
                parent_res = (
                    self.supabase.table(self.config.table_name)
                    .select("*")
                    .in_("node_id", unique_parent_ids)
                    .execute()
                )
                if parent_res.data:
                    for row in parent_res.data:
                        parent_rows_by_id[row["node_id"]] = row
            except Exception as exc:
                logger.warning("Batch fetch for parents failed: %s. Falling back to child content.", exc)

        # 7. Assemble RetrievedParentContext objects
        retrieved_contexts: list[RetrievedParentContext] = []

        for pid, children in parent_to_children.items():
            max_similarity = max(c.similarity for c in children)
            parent_row = parent_rows_by_id.get(pid)

            if parent_row:
                # Successfully found stored parent chunk
                context = RetrievedParentContext(
                    parent_id=pid,
                    source_id=parent_row["source_id"],
                    content=parent_row["content"],
                    similarity=max_similarity,
                    metadata=parent_row.get("metadata") or {},
                    matched_children=children,
                )
            else:
                # Fallback: parent missing in DB, use primary matched child content
                best_child = max(children, key=lambda c: c.similarity)
                context = RetrievedParentContext(
                    parent_id=pid,
                    source_id=best_child.source_id,
                    content=best_child.content,
                    similarity=max_similarity,
                    metadata=best_child.metadata,
                    matched_children=children,
                )
            retrieved_contexts.append(context)

        # Handle any children without parent_ids directly as fallback contexts
        for child in unparented_children:
            retrieved_contexts.append(
                RetrievedParentContext(
                    parent_id=child.node_id,
                    source_id=child.source_id,
                    content=child.content,
                    similarity=child.similarity,
                    metadata=child.metadata,
                    matched_children=[child],
                )
            )

        # Sort parent contexts by highest similarity descending
        retrieved_contexts.sort(key=lambda ctx: ctx.similarity, reverse=True)

        result.retrieved_contexts = retrieved_contexts
        result.total_parents_returned = len(retrieved_contexts)

        return result
