"""
test_chunking.py
================
Layer 2 — splitting long documents and merging short ones.

Chunk boundaries decide what retrieval can return, so these tests are about
boundaries: that they land between sentences, that they overlap by the
configured amount, that a slide is never merged with a different upload, and
that re-ingesting a file reuses its chunk ids instead of duplicating it.
"""

from __future__ import annotations

import pytest
from llama_index.core.schema import Document

from app.services.rag.processing.chunking import DocumentChunker


def _doc(text: str, *, source="s1", page=1, total=1) -> Document:
    doc = Document(
        text=text,
        metadata={
            "source_id": source,
            "file_name": f"{source}.pdf",
            "page_or_slide_num": page,
            "total_pages_or_slides": total,
        },
    )
    doc.excluded_embed_metadata_keys = ["source_id"]
    return doc


def _prose(sentences: int, start: int = 0) -> str:
    """Distinct sentences, so an overlap measurement means something."""
    return " ".join(
        f"Sentence number {i} describes a distinct biological concept."
        for i in range(start, start + sentences)
    )


def _measure_overlap(first: str, second: str) -> int:
    a, b = first.split(), second.split()
    return max(
        (k for k in range(1, min(len(a), len(b)) + 1) if a[-k:] == b[:k]),
        default=0,
    )


# ── Splitting long text ───────────────────────────────────────────────────────

def test_a_long_page_is_split():
    chunker = DocumentChunker(chunk_words=100, overlap_words=20)

    chunks = chunker.chunk_documents([_doc(_prose(120))])

    assert len(chunks) > 1
    assert all(c.metadata["word_count"] <= 100 for c in chunks)


def test_chunks_overlap_by_the_configured_amount():
    """Overlap is what stops a fact that straddles a boundary from being lost
    to both chunks."""
    chunker = DocumentChunker(chunk_words=100, overlap_words=20)

    chunks = chunker.chunk_documents([_doc(_prose(200))])

    assert _measure_overlap(chunks[0].text, chunks[1].text) == pytest.approx(20, abs=8)


def test_chunks_do_not_start_mid_sentence():
    """The reason for a sentence-aware splitter rather than a character count:
    half a sentence embeds to a vector for something nobody said."""
    chunker = DocumentChunker(chunk_words=60, overlap_words=10)

    chunks = chunker.chunk_documents([_doc(_prose(80))])

    for chunk in chunks[1:]:
        assert chunk.text.lstrip().startswith("Sentence number")


def test_a_short_tail_is_folded_into_the_previous_chunk():
    """A splitter working to a fixed size leaves a few words over. Stored
    alone that fragment competes for a retrieval slot while saying nothing."""
    chunker = DocumentChunker(chunk_words=50, overlap_words=5, min_chunk_words=30)

    chunks = chunker.chunk_documents([_doc(_prose(37))])

    assert all(c.metadata["word_count"] >= 30 for c in chunks)


# ── Merging short units ───────────────────────────────────────────────────────

def test_slides_are_merged_until_they_are_worth_retrieving():
    """A 15-word slide embeds to a vague vector that matches everything and
    answers nothing, so slides are combined before any splitting."""
    slides = [
        _doc("Alleles segregate independently during gamete formation.",
             source="deck", page=n, total=6)
        for n in range(1, 7)
    ]

    chunks = DocumentChunker(min_merge_words=20).chunk_documents(slides)

    assert len(chunks) < len(slides)
    assert all(c.metadata["merged_units"] > 1 for c in chunks)


def test_a_merged_chunk_records_the_pages_it_covers():
    """Once one chunk is no longer one slide, a citation needs the range."""
    slides = [_doc("Short slide text here.", source="deck", page=n, total=3) for n in (1, 2, 3)]

    (chunk,) = DocumentChunker(min_merge_words=100).chunk_documents(slides)

    assert chunk.metadata["page_start"] == 1
    assert chunk.metadata["page_end"] == 3
    assert chunk.metadata["merged_units"] == 3


def test_documents_from_different_files_are_never_merged():
    """Slide 3 of one upload must not end up glued to the start of another."""
    docs = [
        _doc("Short text from the first file.", source="a", page=1),
        _doc("Short text from the second file.", source="b", page=1),
    ]

    chunks = DocumentChunker(min_merge_words=500).chunk_documents(docs)

    assert len(chunks) == 2
    assert {c.metadata["source_id"] for c in chunks} == {"a", "b"}


def test_a_long_page_is_not_merged_with_its_neighbour():
    """Merging is for units too small to stand alone, not a general policy —
    over-merging destroys the page boundaries citations depend on."""
    docs = [
        _doc(_prose(60), source="s1", page=1, total=2),
        _doc(_prose(60, start=60), source="s1", page=2, total=2),
    ]

    chunks = DocumentChunker(chunk_words=500, min_merge_words=50).chunk_documents(docs)

    assert [c.metadata["page_start"] for c in chunks] == [1, 2]


# ── Identity and bookkeeping ──────────────────────────────────────────────────

def test_chunk_ids_are_deterministic():
    """Re-ingesting a file should overwrite its chunks in the vector store,
    not silently double them."""
    docs = [_doc(_prose(150))]

    first = DocumentChunker().chunk_documents(docs)
    second = DocumentChunker().chunk_documents(docs)

    assert [c.id_ for c in first] == [c.id_ for c in second]
    assert first[0].id_.startswith("s1:")


def test_chunks_are_numbered_within_their_source():
    docs = [_doc(_prose(200), source="a"), _doc(_prose(200), source="b")]

    chunks = DocumentChunker(chunk_words=100).chunk_documents(docs)

    for source in ("a", "b"):
        indexes = [c.metadata["chunk_index"] for c in chunks if c.metadata["source_id"] == source]
        assert indexes == list(range(len(indexes)))
        assert all(
            c.metadata["total_chunks"] == len(indexes)
            for c in chunks if c.metadata["source_id"] == source
        )


def test_bookkeeping_stays_out_of_the_embedding():
    """A word count and a chunk index inside the embedded text are noise that
    push otherwise similar chunks apart."""
    (chunk,) = DocumentChunker().chunk_documents([_doc(_prose(20))])

    embedded = chunk.get_content(metadata_mode="embed")

    assert "word_count" not in embedded
    assert "chunk_index" not in embedded
    assert "source_id" not in embedded, "inherited from the document's exclusions"
    assert "file_name" in embedded


def test_page_range_reaches_the_llm():
    """The model needs it to say which slide a question came from."""
    (chunk,) = DocumentChunker().chunk_documents([_doc(_prose(20))])

    assert "page_start" in chunk.get_content(metadata_mode="llm")


# ── Edges ─────────────────────────────────────────────────────────────────────

def test_no_documents_means_no_chunks():
    assert DocumentChunker().chunk_documents([]) == []


def test_blank_documents_are_skipped():
    docs = [_doc("   "), _doc(_prose(20), page=2)]

    chunks = DocumentChunker().chunk_documents(docs)

    assert len(chunks) == 1
