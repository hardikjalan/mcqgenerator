"""
test_cleaning.py
================
Text normalisation, and the line-wrap repair that makes PDF chunking possible.

The repair is the interesting half. A PDF stores where each line was printed,
not where sentences end, so extraction yields a newline every ~90 characters
in the middle of sentences — and a real paragraph break looks identical. Left
alone, a sentence-aware splitter cuts on those false boundaries and every
chunk starts on half a thought.
"""

from __future__ import annotations

from app.services.rag.processing.cleaning import (
    DocumentCleaner,
    TextCleaner,
    layout_aware_cleaner,
    repair_line_wraps,
)

WRAPPED = (
    "Photosynthesis is the process by which green plants and certain bacteria "
    "convert light energy\ninto chemical energy stored in glucose. The overall "
    "reaction consumes carbon dioxide and\nreleases oxygen as a byproduct.\n"
    "The light-dependent reactions occur in the thylakoid membrane where "
    "chlorophyll absorbs\nphotons and excites electrons."
)


# ── Standard rules ────────────────────────────────────────────────────────────

def test_invisible_characters_are_stripped():
    """A zero-width space makes two identical words look different to every
    downstream comparison."""
    assert TextCleaner().clean("DNA.​  Ribosomes") == "DNA. Ribosomes"


def test_line_endings_are_unified():
    assert TextCleaner().clean("one\r\ntwo\rthree") == "one\ntwo\nthree"


def test_a_page_break_becomes_a_line_break_not_nothing():
    """Deleting it glues the last word of one page to the first of the next."""
    assert TextCleaner().clean("glucose\x0cThe Calvin cycle") == "glucose\nThe Calvin cycle"


def test_indentation_survives():
    """Runs of spaces collapse, but not at the start of a line — code samples
    and outlines in the source material keep their shape."""
    cleaned = TextCleaner().clean("text\n    indented    words")
    assert cleaned == "text\n    indented words"


# ── Line-wrap repair ──────────────────────────────────────────────────────────

def test_wrapped_sentences_are_rejoined():
    repaired = repair_line_wraps(WRAPPED)

    assert "light energy into chemical energy" in repaired
    assert "carbon dioxide and releases oxygen" in repaired


def test_real_paragraph_breaks_survive():
    """The previous line ended with a full stop, so that newline is real."""
    repaired = repair_line_wraps(WRAPPED)

    assert "byproduct.\nThe light-dependent" in repaired


def test_words_split_across_lines_are_rejoined():
    text = "the process of photosyn-\nthesis is central to plant biology and ecology"
    assert "photosynthesis" in repair_line_wraps(text)


def test_bullets_are_not_joined_to_the_line_above():
    text = (
        "The light reactions depend on several components working together in "
        "the membrane\n"
        "- Chlorophyll absorbs photons\n"
        "- ATP synthase builds ATP"
    )
    repaired = repair_line_wraps(text)

    assert "\n- Chlorophyll" in repaired
    assert "\n- ATP synthase" in repaired


def test_headings_are_not_absorbed_into_the_text_below():
    """A short line is a heading or a table cell, not a wrapped sentence — a
    wrapped line runs nearly the full column width."""
    text = "Chapter 3\nPhotosynthesis is the process by which plants convert light"
    assert repair_line_wraps(text).startswith("Chapter 3\n")


def test_blank_lines_are_left_alone():
    text = "First paragraph runs to the end of the column and wraps here\n\nSecond"
    assert "\n\n" in repair_line_wraps(text)


# ── Wiring ────────────────────────────────────────────────────────────────────

def test_only_the_layout_aware_cleaner_repairs_wraps():
    """Applied to a slide or a Word document this would be wrong — there a
    newline separates a bullet or a paragraph and carries meaning."""
    text = "This line is long enough to look like a wrapped line of body text\nand continues"

    assert "\n" in TextCleaner().clean(text)
    assert "\n" not in layout_aware_cleaner()._text_cleaner.clean(text)


def test_cleaning_preserves_document_identity():
    """Rebuilding the Document instead of mutating it would silently drop the
    metadata attached to it."""
    from llama_index.core.schema import Document

    doc = Document(text="  spaced   out  ", metadata={"file_name": "x.pdf"})
    (cleaned,) = DocumentCleaner().clean_documents([doc])

    assert cleaned.metadata == {"file_name": "x.pdf"}
    assert cleaned.text == "spaced out"
