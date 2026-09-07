"""
manager.py
==========
ChunkingManager — the public API for Layer 3.

Coordinates the full pipeline:

1. **Hierarchy detection**: Parse headings from each document page,
   tracking cross-page state per ``source_id``.
2. **Semantic splitting**: Split each hierarchical section into semantic
   chunks at natural boundaries (paragraph → sentence), protecting
   atomic content (tables, formulas, code).
3. **Parent-child construction**: Group semantic chunks into parent
   windows (≤ ``max_parent_size`` tokens) and generate child nodes
   (~ ``target_chunk_size`` tokens) within each parent.
4. **Metadata & indexing**: Assign ``chunk_index`` / ``total_chunks`` to
   all children for ordering and provenance.

Isolation guarantee: Documents with different ``source_id`` values are
always processed independently.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from copy import deepcopy

from llama_index.core.schema import Document

from app.services.rag.chunking.models import (
    ChunkingConfig,
    ChunkingResult,
    HierarchyContext,
)
from app.services.rag.chunking.hierarchy import (
    HierarchyTracker,
    split_by_headings,
)
from app.services.rag.chunking.semantic import SemanticSplitter
from app.services.rag.chunking.parent_child import ParentChildChunker

logger = logging.getLogger(__name__)


class ChunkingManager:
    """Layer 3 Coordinator: Hierarchical + Semantic + Parent-Child Chunking.

    Usage::

        from app.services.rag.chunking import ChunkingManager, ChunkingConfig

        manager = ChunkingManager(ChunkingConfig(target_chunk_size=512))
        result = manager.chunk_documents(cleaned_docs)
        # result.parent_chunks: list[TextNode]
        # result.child_chunks:  list[TextNode]
    """

    def __init__(self, config: ChunkingConfig | None = None) -> None:
        self.config = config or ChunkingConfig()
        self._semantic_splitter = SemanticSplitter(self.config)
        self._parent_child_chunker = ParentChildChunker(self.config)

    # ── Public API ───────────────────────────────────────────────────────────

    def chunk_documents(self, documents: list[Document]) -> ChunkingResult:
        """Process documents from a **single** ``source_id`` into chunks.

        Parameters
        ----------
        documents : list[Document]
            Cleaned LlamaIndex ``Document`` objects from Layer 2.  All
            documents must share the same ``source_id``.

        Returns
        -------
        ChunkingResult
        """
        if not documents:
            return ChunkingResult()

        # Extract shared metadata from the first document.
        first_meta = documents[0].metadata
        source_id = first_meta.get("source_id", "")
        
        # Ensure all documents have the same source_id.
        for doc in documents:
            if doc.metadata.get("source_id", "") != source_id:
                raise ValueError(
                    f"Documents contain multiple source_ids. Expected {source_id}."
                )

        file_name = first_meta.get("file_name", "")
        file_type = first_meta.get("file_type", "")
        total_pages = first_meta.get("total_pages_or_slides")

        base_metadata = {
            "source_id": source_id,
            "file_name": file_name,
            "file_type": file_type,
            "total_pages_or_slides": total_pages,
        }

        # Copy any custom_metadata from the first document.
        custom = first_meta.get("custom_metadata", {})
        if isinstance(custom, dict):
            base_metadata.update(custom)

        # ── 1. Hierarchy detection + semantic splitting ──────────────────────
        hierarchy_tracker = HierarchyTracker()
        all_semantic_chunks = []

        current_ctx = None
        accumulated_text: list[str] = []
        accumulated_pages: list[int] = []

        def flush_accumulated() -> None:
            if current_ctx and accumulated_text:
                combined_text = "\n\n".join(accumulated_text)
                chunks = self._semantic_splitter.split_section(
                    text=combined_text,
                    hierarchy=deepcopy(current_ctx),
                    page_numbers=sorted(set(accumulated_pages)),
                )
                all_semantic_chunks.extend(chunks)
            accumulated_text.clear()
            accumulated_pages.clear()

        for doc in documents:
            page_num = doc.metadata.get("page_or_slide_num")

            segments = split_by_headings(doc.text)

            for heading, segment_text in segments:
                if heading is not None:
                    flush_accumulated()
                    current_ctx = hierarchy_tracker.update(heading)
                else:
                    if current_ctx is None:
                        current_ctx = hierarchy_tracker.current_context()

                if segment_text:
                    accumulated_text.append(segment_text)
                    if page_num is not None and page_num not in accumulated_pages:
                        accumulated_pages.append(page_num)

        flush_accumulated()

        # ── 2. Parent-child construction ─────────────────────────────────────
        groups = self._parent_child_chunker.build_parent_children(
            semantic_chunks=all_semantic_chunks,
            base_metadata=base_metadata,
        )

        # ── 3. Collect and index ─────────────────────────────────────────────
        all_parents = []
        all_children = []

        for group in groups:
            all_parents.append(group.parent)
            all_children.extend(group.children)

        # Assign chunk_index and total_chunks to each child.
        total_child_count = len(all_children)
        for i, child in enumerate(all_children):
            child.metadata["chunk_index"] = i + 1
            child.metadata["total_chunks"] = total_child_count

        return ChunkingResult(
            source_id=source_id,
            file_name=file_name,
            file_type=file_type,
            parent_chunks=all_parents,
            child_chunks=all_children,
            total_parents=len(all_parents),
            total_children=total_child_count,
        )

    def chunk_document_groups(
        self,
        documents: list[Document],
    ) -> list[ChunkingResult]:
        """Process a batch of documents, grouping by ``source_id``.

        Use this when processing documents from multiple files at once.
        Each ``source_id`` group is processed independently to guarantee
        cross-document isolation.

        Parameters
        ----------
        documents : list[Document]
            Mixed-source documents from Layer 2.

        Returns
        -------
        list[ChunkingResult]
        """
        groups: dict[str, list[Document]] = defaultdict(list)
        for doc in documents:
            sid = doc.metadata.get("source_id", "unknown")
            groups[sid].append(doc)

        results: list[ChunkingResult] = []
        for source_id, group_docs in groups.items():
            try:
                result = self.chunk_documents(group_docs)
                results.append(result)
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Chunking failed for source_id=%s: %s", source_id, exc,
                )
                results.append(ChunkingResult(
                    source_id=source_id,
                    errors=[str(exc)],
                ))

        return results
