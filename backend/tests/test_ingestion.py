"""
test_ingestion.py
=================
Layer 1 — that every supported format comes out the far side looking the same.

The point of the ingestion layer is format erasure, so most of these tests
assert on the *uniformity* of the output rather than on the text itself.
"""

from __future__ import annotations

import shutil

import pytest

from app.services.rag.ingestion import IngestionManager
from app.services.rag.ingestion.detector import FileTypeDetector
from app.services.rag.ingestion.exceptions import (
    CorruptedFileError,
    UnsupportedFileTypeError,
)
from app.services.rag.schemas import SupportedFormat

STANDARD_KEYS = {
    "file_name",
    "file_type",
    "file_size_bytes",
    "source_id",
    "page_or_slide_num",
    "total_pages_or_slides",
    "ingested_at",
}

# Loader- and reader-supplied extras are flattened onto the top level under
# this prefix, so they vary by format and are excluded from the comparison.
CUSTOM_PREFIX = "x_"


# ── Detection ─────────────────────────────────────────────────────────────────

def test_detects_each_format(pdf_path, docx_path, pptx_path):
    assert FileTypeDetector.detect(pdf_path) is SupportedFormat.PDF
    assert FileTypeDetector.detect(docx_path) is SupportedFormat.DOCX
    assert FileTypeDetector.detect(pptx_path) is SupportedFormat.PPTX


def test_detection_ignores_a_lying_extension(pptx_path, tmp_path):
    """A .pptx renamed to .pdf must still be recognised as a .pptx.

    Magic bytes say ZIP, which rules out PDF; the archive's ``ppt/`` folder
    then settles it. This is the case a suffix check gets wrong.
    """
    liar = tmp_path / "actually_a_deck.pdf"
    shutil.copy(pptx_path, liar)
    assert FileTypeDetector.detect(liar) is SupportedFormat.PPTX


def test_unknown_format_is_rejected(tmp_path):
    odd = tmp_path / "notes.xyz"
    odd.write_bytes(b"just some bytes")
    with pytest.raises(UnsupportedFileTypeError):
        FileTypeDetector.detect(odd)


# ── Ingestion ─────────────────────────────────────────────────────────────────

def test_pdf_yields_one_document_per_page(pdf_path):
    result = IngestionManager().ingest_file(pdf_path)

    assert result.file_type == SupportedFormat.PDF.value
    assert result.total_units == 3
    assert result.raw_char_count > 0
    assert [d.metadata["page_or_slide_num"] for d in result.documents] == [1, 2, 3]
    assert all(d.metadata["total_pages_or_slides"] == 3 for d in result.documents)


def test_docx_is_read_without_docx2txt(docx_path):
    """Regression: LlamaIndex's DocxReader needs docx2txt, which is not a
    dependency, so every .docx upload used to fail with a CorruptedFileError."""
    result = IngestionManager().ingest_file(docx_path)

    assert result.total_units == 1
    text = result.documents[0].text
    assert "Mitochondria" in text
    assert "Protein synthesis" in text, "table cells should be extracted too"


def test_pptx_yields_one_document_per_slide(pptx_path):
    result = IngestionManager().ingest_file(pptx_path)

    assert result.total_units == 3
    assert "Punnett" in result.documents[2].text


@pytest.mark.parametrize("fixture", ["pdf_path", "docx_path", "pptx_path"])
def test_metadata_is_identical_across_formats(fixture, request):
    """Format erasure: whatever went in, Layer 2 sees the same keys."""
    path = request.getfixturevalue(fixture)
    result = IngestionManager().ingest_file(path)

    for doc in result.documents:
        standard = {k for k in doc.metadata if not k.startswith(CUSTOM_PREFIX)}
        assert standard == STANDARD_KEYS


def test_metadata_values_are_scalars(pptx_path):
    """Chroma, Pinecone and pgvector all reject non-scalar metadata values.
    A nested dict here would have failed at insert time in Layer 3 — far from
    the code that created it."""
    doc = IngestionManager().ingest_file(pptx_path).documents[0]

    for key, value in doc.metadata.items():
        assert isinstance(value, (str, int, float, bool)) or value is None, key


def test_reader_noise_is_stripped(pptx_path):
    """PptxReader attaches the absolute file path and a full copy of the slide
    text. Neither may survive — one leaks the server filesystem, the other
    doubles the payload of every chunk."""
    doc = IngestionManager().ingest_file(pptx_path).documents[0]

    assert "file_path" not in doc.metadata
    assert "text_sections" not in doc.metadata


def test_bookkeeping_is_hidden_from_the_embedding(pdf_path):
    """A UUID and a timestamp inside the embedded text would push otherwise
    similar chunks apart, so they must be excluded — while the filename and
    page number stay visible to the LLM for citations."""
    doc = IngestionManager().ingest_file(pdf_path).documents[0]

    embedded = doc.get_content(metadata_mode="embed")
    assert doc.metadata["source_id"] not in embedded

    for_llm = doc.get_content(metadata_mode="llm")
    assert "sample.pdf" in for_llm


def test_cleaning_runs_on_ingested_text(docx_path):
    """The fixture contains a zero-width space and a double space."""
    text = IngestionManager().ingest_file(docx_path).documents[0].text

    assert "​" not in text
    assert "DNA. Ribosomes" in text


def test_corrupt_file_raises_a_useful_error(tmp_path):
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.4\nthis is not really a pdf")

    with pytest.raises(CorruptedFileError) as excinfo:
        IngestionManager().ingest_file(broken)

    assert "broken.pdf" in excinfo.value.message


def test_ingest_bytes_matches_ingest_file(pdf_path):
    """The Supabase path goes through ingest_bytes, so it must agree."""
    from_disk = IngestionManager().ingest_file(pdf_path)
    from_bytes = IngestionManager().ingest_bytes(pdf_path.read_bytes(), "sample.pdf")

    assert from_bytes.total_units == from_disk.total_units
    assert from_bytes.raw_char_count == from_disk.raw_char_count
