"""
test_legacy_ppt.py
==================
The legacy binary formats (.doc, .ppt) — registration and the .doc fallback
chain.

The chain is the point. ``win32com`` needs Microsoft Word and ``antiword``
needs a system binary, and Railway and Render have neither, so before the
salvage fallback existed every .doc upload succeeded on a Windows laptop and
failed in production. These tests pin the order and pin the fact that the last
link in the chain has no external dependency.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.rag.ingestion.loaders.doc_loader import DocLegacyLoader
from app.services.rag.ingestion.registry import loader_registry
from app.services.rag.schemas import SupportedFormat


def test_legacy_loaders_are_registered():
    assert loader_registry.has(SupportedFormat.DOC)
    assert loader_registry.has(SupportedFormat.PPT)


def _fail(*args, **kwargs):
    raise RuntimeError("not available on this host")


def test_com_is_preferred_when_available(monkeypatch):
    monkeypatch.setattr(DocLegacyLoader, "_extract_via_com", staticmethod(lambda p: "from word"))

    text, method = DocLegacyLoader()._extract_text_with_fallbacks(Path("x.doc"))

    assert (text, method) == ("from word", "win32com")


def test_falls_back_to_antiword(monkeypatch):
    monkeypatch.setattr(DocLegacyLoader, "_extract_via_com", staticmethod(_fail))
    monkeypatch.setattr(
        DocLegacyLoader, "_extract_via_antiword", staticmethod(lambda p: "from antiword")
    )

    text, method = DocLegacyLoader()._extract_text_with_fallbacks(Path("x.doc"))

    assert (text, method) == ("from antiword", "antiword")


def test_falls_back_to_salvage_when_no_binaries_exist(monkeypatch):
    """The deployment case: neither Word nor antiword is installed."""
    monkeypatch.setattr(DocLegacyLoader, "_extract_via_com", staticmethod(_fail))
    monkeypatch.setattr(DocLegacyLoader, "_extract_via_antiword", staticmethod(_fail))
    monkeypatch.setattr(
        DocLegacyLoader, "_extract_via_salvage", staticmethod(lambda p: "salvaged text")
    )

    text, method = DocLegacyLoader()._extract_text_with_fallbacks(Path("x.doc"))

    assert (text, method) == ("salvaged text", "ole2_salvage")


def test_the_error_names_every_attempt(monkeypatch):
    """When all three fail, the diagnostics have to say so — a single
    'could not read' message sends the next person guessing."""
    from app.services.rag.ingestion.exceptions import CorruptedFileError

    for name in ("_extract_via_com", "_extract_via_antiword", "_extract_via_salvage"):
        monkeypatch.setattr(DocLegacyLoader, name, staticmethod(_fail))

    with pytest.raises(CorruptedFileError):
        DocLegacyLoader()._extract_text_with_fallbacks(Path("x.doc"))
