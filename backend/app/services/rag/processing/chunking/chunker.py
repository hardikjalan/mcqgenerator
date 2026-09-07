"""
chunker.py
==========
RAG Layer 2 — turning whole documents into retrievable chunks.

A chunk is the unit of retrieval: the pipeline searches chunks, and whatever
comes back is what the model sees. That makes chunk boundaries a quality
decision, not a formatting one. Two failures matter:

* **Too large** — a whole 3,000-word page retrieved for one relevant sentence
  buries the answer in unrelated text, and the embedding averages so many
  topics that it matches nothing sharply.
* **Too small** — a 15-word slide embeds to a vague vector that is weakly
  similar to everything, so it surfaces for unrelated questions and crowds out
  better matches.

The sources here fail in opposite directions, which is why this module does
two different things rather than one:

* A PDF page or a Word document is long, so it is **split**.
* A PowerPoint slide averages about 90 characters — fifteen words — so it is
  **merged** with its neighbours before any splitting is considered.

Splitting is delegated to LlamaIndex's ``SentenceSplitter``, which respects
sentence boundaries rather than cutting at a character count. It is given a
word-based tokenizer; see ``app/config.py`` for why not tokens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import Document, TextNode

from app import config


def _count_words(text: str) -> list[str]:
    """Tokenizer handed to SentenceSplitter: one 'token' is one word."""
    return text.split()


@dataclass
class _Unit:
    """One or more consecutive documents treated as a single body of text."""

    text: str
    metadata: dict[str, Any]
    page_start: int | None
    page_end: int | None
    source_id: str | None
    merged_from: int = 1
    excluded_embed: list[str] = field(default_factory=list)
    excluded_llm: list[str] = field(default_factory=list)


class DocumentChunker:
    """Splits and merges Documents into retrieval-sized ``TextNode`` chunks."""

    def __init__(
        self,
        *,
        chunk_words: int | None = None,
        overlap_words: int | None = None,
        min_merge_words: int | None = None,
        min_chunk_words: int | None = None,
    ) -> None:
        self.chunk_words = chunk_words or config.CHUNK_SIZE_WORDS
        self.overlap_words = overlap_words or config.CHUNK_OVERLAP_WORDS
        self.min_merge_words = min_merge_words or config.MIN_MERGE_WORDS
        self.min_chunk_words = min_chunk_words or config.MIN_CHUNK_WORDS

        self._splitter = SentenceSplitter(
            chunk_size=self.chunk_words,
            chunk_overlap=self.overlap_words,
            tokenizer=_count_words,
        )

    # ── Public API ────────────────────────────────────────────────────────

    def chunk_documents(self, docs: list[Document]) -> list[TextNode]:
        """Turn ingested Documents into chunks, in reading order.

        Every chunk keeps its source document's metadata, so a retrieved chunk
        can always say which file and which page or slide it came from.
        """
        if not docs:
            return []

        chunks: list[TextNode] = []
        for unit in self._merge_small_units(docs):
            chunks.extend(self._split_unit(unit))

        return self._number(chunks)

    # ── Merging ───────────────────────────────────────────────────────────

    def _merge_small_units(self, docs: list[Document]) -> list[_Unit]:
        """Combine consecutive undersized documents into workable units.

        Only *consecutive* documents from the *same file* are merged, so slide
        3 never ends up glued to the start of a different upload. A merged unit
        records the page range it covers, which is what a citation needs once
        one chunk no longer maps to one slide.
        """
        units: list[_Unit] = []
        pending: list[Document] = []

        def flush() -> None:
            if pending:
                units.append(_to_unit(pending))
                pending.clear()

        for doc in docs:
            if not doc.text.strip():
                continue

            same_source = (
                pending
                and pending[-1].metadata.get("source_id") == doc.metadata.get("source_id")
            )
            if pending and not same_source:
                flush()

            pending.append(doc)

            # Keep accumulating only while the run is still too small to stand
            # on its own. Once it is big enough, close it — over-merging would
            # undo the page boundaries that make citation possible.
            if _words(pending) >= self.min_merge_words:
                flush()

        flush()
        return units

    # ── Splitting ─────────────────────────────────────────────────────────

    def _split_unit(self, unit: _Unit) -> list[TextNode]:
        """Split one unit into chunks, folding away undersized tails."""
        pieces = self._splitter.split_text(unit.text)
        pieces = _fold_short_tail(pieces, self.min_chunk_words)

        nodes: list[TextNode] = []
        for piece in pieces:
            metadata = dict(unit.metadata)
            metadata["page_start"] = unit.page_start
            metadata["page_end"] = unit.page_end
            metadata["merged_units"] = unit.merged_from
            metadata["word_count"] = len(piece.split())

            node = TextNode(text=piece, metadata=metadata)
            # Chunk bookkeeping is for filtering and display, never for the
            # embedding — a word count inside the embedded text is noise.
            node.excluded_embed_metadata_keys = [
                *unit.excluded_embed,
                "page_start", "page_end", "merged_units", "word_count",
                "chunk_index", "total_chunks",
            ]
            node.excluded_llm_metadata_keys = [
                *unit.excluded_llm,
                "merged_units", "word_count", "chunk_index", "total_chunks",
            ]
            nodes.append(node)

        return nodes

    # ── Identity ──────────────────────────────────────────────────────────

    @staticmethod
    def _number(chunks: list[TextNode]) -> list[TextNode]:
        """Number chunks per source and give each a deterministic id.

        The id is ``<source_id>:<n>`` rather than a fresh UUID so that
        re-ingesting the same file overwrites its old chunks in the vector
        store instead of silently doubling them.
        """
        totals: dict[str, int] = {}
        for chunk in chunks:
            key = str(chunk.metadata.get("source_id", ""))
            totals[key] = totals.get(key, 0) + 1

        seen: dict[str, int] = {}
        for chunk in chunks:
            key = str(chunk.metadata.get("source_id", ""))
            index = seen.get(key, 0)
            seen[key] = index + 1

            chunk.metadata["chunk_index"] = index
            chunk.metadata["total_chunks"] = totals[key]
            chunk.id_ = f"{key}:{index}"

        return chunks


# ── Helpers ───────────────────────────────────────────────────────────────────

def _words(docs: list[Document]) -> int:
    return sum(len(doc.text.split()) for doc in docs)


def _to_unit(docs: list[Document]) -> _Unit:
    """Build a unit from one or more consecutive documents."""
    first = docs[0]
    pages = [
        doc.metadata.get("page_or_slide_num")
        for doc in docs
        if doc.metadata.get("page_or_slide_num") is not None
    ]

    return _Unit(
        # Blank line between merged units: it is a paragraph break to a
        # sentence splitter, so it will prefer to cut there if it has to cut.
        text="\n\n".join(doc.text for doc in docs),
        metadata=dict(first.metadata),
        page_start=min(pages) if pages else None,
        page_end=max(pages) if pages else None,
        source_id=first.metadata.get("source_id"),
        merged_from=len(docs),
        excluded_embed=list(first.excluded_embed_metadata_keys or []),
        excluded_llm=list(first.excluded_llm_metadata_keys or []),
    )


def _fold_short_tail(pieces: list[str], minimum: int) -> list[str]:
    """Append an undersized final piece to the one before it.

    A splitter working to a fixed size regularly leaves a few words over at
    the end. Stored alone that fragment is a chunk with almost no meaning that
    still competes for a retrieval slot.
    """
    if len(pieces) > 1 and len(pieces[-1].split()) < minimum:
        pieces = pieces[:-1] + [f"{pieces[-2]}\n{pieces[-1]}"]
        pieces.pop(-2)
    return pieces
