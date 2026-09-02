"""
detector.py
===========
Reliable file-type identification using three signals:

1. **Magic bytes** — the first few bytes of the file (most trustworthy).
2. **MIME type** — from Python's ``mimetypes`` module.
3. **Extension** — the filename suffix (least trustworthy, but useful as a
   tiebreaker when magic bytes match a container format like ZIP or OLE2).

The detector never trusts the client-provided extension alone because files
can be renamed or mislabelled.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from app.services.rag.schemas import SupportedFormat
from app.services.rag.ingestion.exceptions import UnsupportedFileTypeError


# ── Magic byte signatures ────────────────────────────────────────────────────

_PDF_MAGIC = b"%PDF-"

# ZIP-based Office Open XML (.docx, .pptx)
_ZIP_MAGIC = b"PK\x03\x04"

# OLE2 Compound Document (.doc, .ppt, .xls)
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


# ── Extension → format lookup ────────────────────────────────────────────────

_EXT_MAP: dict[str, SupportedFormat] = {
    ".pdf":  SupportedFormat.PDF,
    ".docx": SupportedFormat.DOCX,
    ".doc":  SupportedFormat.DOC,
    ".pptx": SupportedFormat.PPTX,
    ".ppt":  SupportedFormat.PPT,
}

# MIME → format (used when magic bytes match a container and we need to
# disambiguate via MIME).
_MIME_MAP: dict[str, SupportedFormat] = {
    "application/pdf": SupportedFormat.PDF,
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document":   SupportedFormat.DOCX,
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": SupportedFormat.PPTX,
    "application/msword": SupportedFormat.DOC,
    "application/vnd.ms-powerpoint": SupportedFormat.PPT,
}


class FileTypeDetector:
    """
    Detect the ``SupportedFormat`` of a file using magic bytes, MIME, and
    extension — in that priority order.

    Usage::

        fmt = FileTypeDetector.detect(Path("lecture.pdf"))
        # → SupportedFormat.PDF
    """

    @staticmethod
    def detect(file_path: Path) -> SupportedFormat:
        """
        Return the detected format or raise ``UnsupportedFileTypeError``.

        Parameters
        ----------
        file_path:
            Path to the file on disk.  Must exist and be readable.
        """
        header = _read_header(file_path, 8)
        ext = file_path.suffix.lower()

        # ── 1. Magic bytes ────────────────────────────────────────────────
        if header.startswith(_PDF_MAGIC):
            return SupportedFormat.PDF

        if header.startswith(_ZIP_MAGIC):
            # ZIP container: could be .docx or .pptx — use extension to
            # disambiguate.
            if ext == ".docx":
                return SupportedFormat.DOCX
            if ext == ".pptx":
                return SupportedFormat.PPTX
            # Try MIME as a fallback before giving up.
            mime_fmt = _detect_from_mime(file_path)
            if mime_fmt and mime_fmt in (SupportedFormat.DOCX, SupportedFormat.PPTX):
                return mime_fmt
            # If we still don't know, try probing the ZIP contents.
            return _probe_zip_contents(file_path, ext)

        if header.startswith(_OLE2_MAGIC):
            # OLE2 container: could be .doc or .ppt — extension decides.
            if ext == ".doc":
                return SupportedFormat.DOC
            if ext == ".ppt":
                return SupportedFormat.PPT
            mime_fmt = _detect_from_mime(file_path)
            if mime_fmt and mime_fmt in (SupportedFormat.DOC, SupportedFormat.PPT):
                return mime_fmt
            # Default to .doc for OLE2 without a clearer signal.
            return SupportedFormat.DOC

        # ── 2. Extension fallback ─────────────────────────────────────────
        if ext in _EXT_MAP:
            return _EXT_MAP[ext]

        # ── 3. MIME fallback ──────────────────────────────────────────────
        mime_fmt = _detect_from_mime(file_path)
        if mime_fmt:
            return mime_fmt

        raise UnsupportedFileTypeError(file_path.name, detected=ext or None)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _read_header(path: Path, n: int) -> bytes:
    """Read the first *n* bytes of *path*."""
    with open(path, "rb") as f:
        return f.read(n)


def _detect_from_mime(path: Path) -> SupportedFormat | None:
    """Return a format based on mimetypes guessing, or None."""
    mime, _ = mimetypes.guess_type(str(path))
    if mime:
        return _MIME_MAP.get(mime)
    return None


def _probe_zip_contents(file_path: Path, ext: str) -> SupportedFormat:
    """
    Open the ZIP archive and look for characteristic paths to distinguish
    DOCX from PPTX when the extension is ambiguous or missing.
    """
    import zipfile

    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()
            if any(n.startswith("word/") for n in names):
                return SupportedFormat.DOCX
            if any(n.startswith("ppt/") for n in names):
                return SupportedFormat.PPTX
    except zipfile.BadZipFile:
        pass

    raise UnsupportedFileTypeError(file_path.name, detected=ext or "zip-based")
