"""
test_extraction.py
==================
The orchestration layer — per-file isolation, guards, and the size budget.

``download`` is patched out throughout: these tests are about what happens
around the network call, not about httpx.
"""

from __future__ import annotations

import pytest

from app.services import extraction
from app.services.extraction import SourceInput, extract_sources
from app.services.rag.ingestion.fetcher import DownloadError


# ``serve`` lives in conftest.py — the retrieval tests need it too.


def _source(name: str, size: int = 1000) -> SourceInput:
    return SourceInput(name=name, signed_url=f"https://example.test/{name}", size_bytes=size)


# ── The happy path ────────────────────────────────────────────────────────────

def test_extracts_a_pdf(serve, pdf_path):
    serve({"sample.pdf": pdf_path.read_bytes()})

    (result,) = extract_sources([_source("sample.pdf")])

    assert result.ok
    assert result.chars > 0
    assert len(result.documents) == 3


# ── Isolation ─────────────────────────────────────────────────────────────────

def test_one_bad_file_does_not_sink_the_batch(serve, pdf_path):
    """The whole reason the service returns rows instead of raising."""
    serve({
        "good.pdf": pdf_path.read_bytes(),
        "gone.pdf": DownloadError("Could not download gone.pdf."),
        "also_good.pdf": pdf_path.read_bytes(),
    })

    results = extract_sources([
        _source("good.pdf"), _source("gone.pdf"), _source("also_good.pdf")
    ])

    assert [r.ok for r in results] == [True, False, True]
    assert results[1].error == "Could not download gone.pdf."


def test_results_keep_request_order(serve, pdf_path):
    """The dashboard matches rows to the files it displayed by position."""
    names = ["a.pdf", "b.pdf", "c.pdf"]
    serve({n: pdf_path.read_bytes() for n in names})

    results = extract_sources([_source(n) for n in names])

    assert [r.name for r in results] == names


def test_an_unexpected_error_becomes_a_row_not_a_crash(serve, monkeypatch, pdf_path):
    serve({"boom.pdf": pdf_path.read_bytes()})

    class Exploding:
        def ingest_bytes(self, content, file_name):
            raise RuntimeError("something nobody predicted")

    (result,) = extract_sources([_source("boom.pdf")], manager=Exploding())

    assert result.ok is False
    assert "something nobody predicted" not in (result.error or ""), (
        "internal messages must not reach the user"
    )


# ── Guards ────────────────────────────────────────────────────────────────────

def test_images_are_rejected_when_ocr_is_off(serve, monkeypatch):
    """The upload widget accepts PNG and JPG. With no OCR provider the user
    needs to be told that text recognition is off — not given a generic
    'unsupported file type' that contradicts the UI that just accepted it."""
    monkeypatch.setattr(extraction.config, "ocr_enabled", lambda: False)
    serve({})

    results = extract_sources([_source("diagram.png"), _source("photo.JPEG")])

    assert [r.ok for r in results] == [False, False]
    assert all("isn't switched on" in r.error for r in results)


def test_images_are_not_downloaded_when_ocr_is_off(monkeypatch):
    """Rejecting before the network call, not after — paying for a transfer
    to reach a foregone conclusion helps nobody."""
    monkeypatch.setattr(extraction.config, "ocr_enabled", lambda: False)

    def explode(*args, **kwargs):
        raise AssertionError("download should not be called for an image")

    monkeypatch.setattr(extraction, "download", explode)
    extract_sources([_source("diagram.png")])


def test_images_reach_the_pipeline_when_ocr_is_on(serve, monkeypatch):
    """With a provider configured the short-circuit must not fire, or the
    image loader would never run."""
    monkeypatch.setattr(extraction.config, "ocr_enabled", lambda: True)
    serve({"diagram.png": b"\x89PNG\r\n\x1a\nnot really a png"})

    downloaded = []

    class Recording:
        def ingest_bytes(self, content, file_name):
            downloaded.append(file_name)
            raise RuntimeError("stop here — the point is that we got this far")

    extract_sources([_source("diagram.png")], manager=Recording())

    assert downloaded == ["diagram.png"]


def test_cumulative_budget_stops_later_files(serve, pdf_path):
    """The browser caps the combined size, which is exactly why the server
    must too — a request is just JSON and the cap is trivially bypassed."""
    payload = pdf_path.read_bytes()
    serve({f"f{i}.pdf": payload for i in range(3)})

    size = extraction.MAX_CUMULATIVE_BYTES  # one file exhausts the budget
    results = extract_sources([
        SourceInput("f0.pdf", "https://example.test/0", size),
        SourceInput("f1.pdf", "https://example.test/1", size),
        SourceInput("f2.pdf", "https://example.test/2", size),
    ])

    assert results[0].ok is True
    assert [r.ok for r in results[1:]] == [False, False]
    assert "combined size" in results[1].error


def test_a_failed_file_does_not_consume_budget(serve, pdf_path):
    serve({
        "gone.pdf": DownloadError("nope"),
        "good.pdf": pdf_path.read_bytes(),
    })

    size = extraction.MAX_CUMULATIVE_BYTES
    results = extract_sources([
        SourceInput("gone.pdf", "https://example.test/0", size),
        SourceInput("good.pdf", "https://example.test/1", size),
    ])

    assert results[1].ok is True, "a download that failed should cost nothing"
