"""
test_ocr.py
===========
The OCR layer: provider selection, the image loader, and the scanned-PDF
fallback.

No real vision API is called. A fake provider is injected instead, because
what needs testing is the plumbing around OCR — when it runs, when it is
skipped, what happens when it returns nothing — not whether Gemini can read
letters.
"""

from __future__ import annotations

import pytest

from app.services.rag.ingestion import IngestionManager
from app.services.rag.ingestion import ocr as ocr_module
from app.services.rag.ingestion.detector import FileTypeDetector
from app.services.rag.ingestion.exceptions import EmptyDocumentError
from app.services.rag.ingestion.ocr import OCRUnavailableError
from app.services.rag.ingestion.ocr.gemini import _clean
from app.services.rag.schemas import SupportedFormat

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class FakeOCR:
    """Returns a fixed answer and records every call."""

    name = "fake"

    def __init__(self, answer: str = "Recovered text from the image") -> None:
        self.answer = answer
        self.calls: list[str] = []

    def extract_text(self, image: bytes, *, mime_type: str, file_name: str) -> str:
        self.calls.append(file_name)
        return self.answer


@pytest.fixture
def with_ocr(monkeypatch):
    """Install a fake provider and hand it back for assertions."""

    def _install(answer: str = "Recovered text from the image") -> FakeOCR:
        provider = FakeOCR(answer)
        monkeypatch.setattr(ocr_module, "get_provider", lambda: provider)
        return provider

    return _install


@pytest.fixture
def without_ocr(monkeypatch):
    monkeypatch.setattr(ocr_module, "get_provider", lambda: None)


@pytest.fixture
def png_path(tmp_path):
    path = tmp_path / "diagram.png"
    path.write_bytes(PNG_MAGIC + b"\x00" * 64)
    return path


# ── Provider selection ────────────────────────────────────────────────────────

def test_no_provider_without_an_api_key(monkeypatch):
    """OCR is optional: an unconfigured deployment must still ingest PDFs."""
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert ocr_module.get_provider() is None


def test_provider_is_built_when_configured(monkeypatch):
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    provider = ocr_module.get_provider()

    assert provider is not None and provider.name == "gemini"


# ── Detection ─────────────────────────────────────────────────────────────────

def test_images_are_detected(png_path, tmp_path):
    assert FileTypeDetector.detect(png_path) is SupportedFormat.PNG

    jpeg = tmp_path / "photo.jpg"
    jpeg.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 32)
    assert FileTypeDetector.detect(jpeg) is SupportedFormat.JPG


def test_a_png_named_pdf_is_still_a_png(tmp_path):
    liar = tmp_path / "slide.pdf"
    liar.write_bytes(PNG_MAGIC + b"\x00" * 64)
    assert FileTypeDetector.detect(liar) is SupportedFormat.PNG


# ── Image loader ──────────────────────────────────────────────────────────────

def test_image_says_ocr_is_off_rather_than_unsupported(png_path, without_ocr):
    """The upload widget accepted this file. 'Unsupported file type' would
    read as a bug; the truth is that text recognition is switched off."""
    with pytest.raises(OCRUnavailableError) as excinfo:
        IngestionManager().ingest_file(png_path)

    assert "isn't switched on" in excinfo.value.message


def test_image_text_is_extracted(png_path, with_ocr):
    provider = with_ocr()

    result = IngestionManager().ingest_file(png_path)

    assert provider.calls == ["diagram.png"]
    assert result.documents[0].text == "Recovered text from the image"
    assert result.documents[0].metadata["x_extraction_method"] == "ocr:fake"


def test_an_image_with_no_text_is_empty_not_broken(png_path, with_ocr):
    """A provider that reads nothing is not a provider that failed."""
    with_ocr(answer="   ")

    with pytest.raises(EmptyDocumentError):
        IngestionManager().ingest_file(png_path)


# ── Scanned PDFs ──────────────────────────────────────────────────────────────

@pytest.fixture
def part_scanned_pdf(tmp_path):
    """Two pages: one with a text layer, one without.

    A page with no text layer is what a scan looks like to pypdf — the words
    are in an image, and the extractor correctly returns nothing.
    """
    import pymupdf

    path = tmp_path / "mixed.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 720), "Chlorophyll absorbs light energy in the thylakoid.")
    doc.new_page()  # deliberately empty
    doc.save(path)
    doc.close()
    return path


def test_a_page_with_no_text_layer_is_ocred(part_scanned_pdf, with_ocr):
    provider = with_ocr(answer="Text recovered from the scan")

    result = IngestionManager().ingest_file(part_scanned_pdf)

    assert len(provider.calls) == 1, "only the page without a text layer"
    assert "page 2" in provider.calls[0]
    assert "Chlorophyll" in result.documents[0].text
    assert result.documents[1].text == "Text recovered from the scan"
    assert result.documents[1].metadata["x_extraction_method"] == "ocr"


def test_pages_with_text_are_left_alone(part_scanned_pdf, with_ocr):
    """OCR is a paid call per page — never spend one on a page that already
    has its text."""
    provider = with_ocr()
    IngestionManager().ingest_file(part_scanned_pdf)

    assert all("page 1" not in call for call in provider.calls)


def test_ocr_is_capped_per_document(tmp_path, with_ocr, monkeypatch):
    """A 300-page scanned book would otherwise issue 300 vision calls from a
    single upload."""
    import pymupdf

    from app import config
    monkeypatch.setattr(config, "MAX_OCR_PAGES_PER_DOC", 3)

    path = tmp_path / "scanned.pdf"
    doc = pymupdf.open()
    for _ in range(10):
        doc.new_page()
    doc.save(path)
    doc.close()

    provider = with_ocr()
    IngestionManager().ingest_file(path)

    assert len(provider.calls) == 3


def test_scanned_pdf_without_ocr_still_fails_clearly(tmp_path, without_ocr):
    import pymupdf

    path = tmp_path / "scanned.pdf"
    doc = pymupdf.open()
    doc.new_page()
    doc.save(path)
    doc.close()

    with pytest.raises(EmptyDocumentError) as excinfo:
        IngestionManager().ingest_file(path)

    assert "images" in excinfo.value.message


def test_a_failing_provider_does_not_break_the_document(part_scanned_pdf, monkeypatch):
    """One unreadable page must not lose the pages that read fine."""

    class Broken:
        name = "broken"

        def extract_text(self, image, *, mime_type, file_name):
            raise RuntimeError("vision API is down")

    monkeypatch.setattr(ocr_module, "get_provider", lambda: Broken())

    result = IngestionManager().ingest_file(part_scanned_pdf)

    assert "Chlorophyll" in result.documents[0].text


# ── Prompt handling ───────────────────────────────────────────────────────────

def test_a_narrated_empty_page_counts_as_no_text():
    """Asked to transcribe a blank page, a vision model often narrates instead.
    That narration must not become course material."""
    assert _clean("This image contains no legible text.") == ""
    assert _clean("  Mitochondria generate ATP.  ") == "Mitochondria generate ATP."
