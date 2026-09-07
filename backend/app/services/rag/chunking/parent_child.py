"""
parent_child.py
===============
Parent window generation and child chunk construction with relationship linking.

Responsibilities:
- Create parent nodes that provide broader context for understanding / MCQ
  generation.
- If a hierarchical/semantic section exceeds ``max_parent_size``, split it
  into multiple **parent windows** at semantic boundaries, with children
  created strictly within each window.
- Create child nodes as precise retrieval units (~``target_chunk_size``
  tokens) linked back to their parent via ``NodeRelationship.PARENT``.
- Guarantee document isolation: parent-child links never cross
  ``source_id`` boundaries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from llama_index.core.schema import NodeRelationship, RelatedNodeInfo, TextNode

from app.services.rag.chunking.models import (
    ChunkingConfig,
    HierarchyContext,
    SemanticType,
    count_tokens,
)
from app.services.rag.chunking.semantic import SemanticChunk, SemanticSplitter


# ── Data structures for parent-child output ──────────────────────────────────

@dataclass
class ParentChildGroup:
    """A parent node and its associated child nodes."""

    parent: TextNode
    children: list[TextNode] = field(default_factory=list)


# ── Parent-child chunker ─────────────────────────────────────────────────────

class ParentChildChunker:
    """Creates parent windows and child chunks from semantic chunks.

    Each parent window is ≤ ``max_parent_size`` tokens.  If the input
    semantic chunks for a section exceed that limit, multiple parent
    windows are created at semantic-chunk boundaries.

    Children are generated within each parent window at approximately
    ``target_chunk_size`` tokens with ``chunk_overlap`` token overlap.
    """

    def __init__(self, config: ChunkingConfig) -> None:
        self.config = config
        self._semantic_splitter = SemanticSplitter(config)

    def build_parent_children(
        self,
        semantic_chunks: list[SemanticChunk],
        base_metadata: dict,
    ) -> list[ParentChildGroup]:
        """Group *semantic_chunks* into parent windows and create children.

        Parameters
        ----------
        semantic_chunks : list[SemanticChunk]
            Ordered semantic chunks for a single document section (or the
            entire document if no headings were detected).
        base_metadata : dict
            Metadata template containing ``source_id``, ``file_name``,
            ``file_type``, ``total_pages_or_slides``, ``custom_metadata``, etc.

        Returns
        -------
        list[ParentChildGroup]
        """
        if not semantic_chunks:
            return []

        # 1. Group semantic chunks into parent windows.
        windows = self._create_parent_windows(semantic_chunks)

        # 2. For each window, create the parent node and its children.
        groups: list[ParentChildGroup] = []
        for window_chunks in windows:
            group = self._build_group(window_chunks, base_metadata)
            if group is not None:
                groups.append(group)

        return groups

    # ── Private helpers ──────────────────────────────────────────────────────

    def _create_parent_windows(
        self,
        chunks: list[SemanticChunk],
    ) -> list[list[SemanticChunk]]:
        """Partition *chunks* into windows each ≤ ``max_parent_size`` tokens."""
        max_size = self.config.max_parent_size
        windows: list[list[SemanticChunk]] = []
        current_window: list[SemanticChunk] = []
        current_tokens = 0

        for chunk in chunks:
            chunk_tokens = count_tokens(chunk.text, self.config)
            join_cost = count_tokens("\n\n", self.config) if current_window else 0

            if current_tokens + join_cost + chunk_tokens > max_size and current_window:
                windows.append(current_window)
                current_window = []
                current_tokens = 0
                join_cost = 0

            current_window.append(chunk)
            current_tokens += join_cost + chunk_tokens

        if current_window:
            windows.append(current_window)

        return windows

    def _build_group(
        self,
        window_chunks: list[SemanticChunk],
        base_metadata: dict,
    ) -> ParentChildGroup | None:
        """Build a ParentChildGroup from a parent window's semantic chunks."""
        if not window_chunks:
            return None

        # ── Assemble parent text ─────────────────────────────────────────────
        # Prepend hierarchy breadcrumb for context.
        hierarchy = window_chunks[0].hierarchy
        breadcrumb = hierarchy.to_header_path()
        parent_text_parts: list[str] = []
        if breadcrumb:
            parent_text_parts.append(f"[{breadcrumb}]")
        for sc in window_chunks:
            parent_text_parts.append(sc.text)

        parent_text = "\n\n".join(parent_text_parts)

        if not parent_text.strip():
            return None

        # ── Collect page numbers ─────────────────────────────────────────────
        all_pages: list[int] = []
        for sc in window_chunks:
            for p in sc.page_numbers:
                if p not in all_pages:
                    all_pages.append(p)
        all_pages.sort()

        primary_page = all_pages[0] if all_pages else base_metadata.get("page_or_slide_num")

        # ── Create parent node ───────────────────────────────────────────────
        parent_id = str(uuid.uuid4())
        parent_meta = {
            **base_metadata,
            "node_id": parent_id,
            "parent_id": None,
            "is_parent": True,
            "hierarchy_level": hierarchy.level,
            "heading": hierarchy.heading,
            "chapter": hierarchy.chapter,
            "section": hierarchy.section,
            "subsection": hierarchy.subsection,
            "page_or_slide_num": primary_page,
            "page_numbers": all_pages,
            "semantic_type": SemanticType.GENERAL.value,  # parents use general
        }

        parent_node = TextNode(
            text=parent_text,
            id_=parent_id,
            metadata=parent_meta,
        )

        # ── Create child nodes ───────────────────────────────────────────────
        children = self._create_children(
            window_chunks=window_chunks,
            parent_node=parent_node,
            base_metadata=base_metadata,
        )

        # ── Link parent → children ───────────────────────────────────────────
        child_infos = [
            RelatedNodeInfo(node_id=c.node_id)
            for c in children
        ]
        parent_node.relationships[NodeRelationship.CHILD] = child_infos

        return ParentChildGroup(parent=parent_node, children=children)

    def _create_children(
        self,
        window_chunks: list[SemanticChunk],
        parent_node: TextNode,
        base_metadata: dict,
    ) -> list[TextNode]:
        """Create child nodes from the semantic chunks within a parent window."""
        children: list[TextNode] = []
        for sc in window_chunks:
            child = self._make_child_node(
                text=sc.text,
                parent_id=parent_node.node_id,
                hierarchy=sc.hierarchy,
                semantic_type=sc.semantic_type,
                page_numbers=sc.page_numbers,
                base_metadata=base_metadata,
            )
            children.append(child)

        return children

    def _make_child_node(
        self,
        text: str,
        parent_id: str,
        hierarchy: HierarchyContext,
        semantic_type: SemanticType,
        page_numbers: list[int],
        base_metadata: dict,
    ) -> TextNode:
        """Construct a single child ``TextNode`` with full metadata."""
        child_id = str(uuid.uuid4())
        primary_page = page_numbers[0] if page_numbers else base_metadata.get("page_or_slide_num")

        child_meta = {
            **base_metadata,
            "node_id": child_id,
            "parent_id": parent_id,
            "is_parent": False,
            "hierarchy_level": hierarchy.level,
            "heading": hierarchy.heading,
            "chapter": hierarchy.chapter,
            "section": hierarchy.section,
            "subsection": hierarchy.subsection,
            "page_or_slide_num": primary_page,
            "page_numbers": page_numbers,
            "semantic_type": semantic_type.value,
        }

        child_node = TextNode(
            text=text,
            id_=child_id,
            metadata=child_meta,
        )
        child_node.relationships[NodeRelationship.PARENT] = RelatedNodeInfo(
            node_id=parent_id,
        )
        return child_node

