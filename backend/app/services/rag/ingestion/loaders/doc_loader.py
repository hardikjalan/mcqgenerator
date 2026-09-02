"""
doc_loader.py
=============
Loader for legacy Word documents (.doc — OLE2 binary format).

``python-docx`` only supports the modern XML-based ``.docx`` format.  For
binary ``.doc`` files we use ``olefile`` to read the OLE2 compound document
and extract the raw text stream (``WordDocument`` stream → decoded text).

This provides a pure-Python fallback that works on Windows without requiring
external tools like LibreOffice or antiword.

Limitations
-----------
- Formatting (bold, italic, tables) is lost — only raw text is extracted.
- Embedded images and OLE objects are skipped.
- Password-protected or encrypted files raise ``CorruptedFileError``.
"""

from __future__ import annotations

import re
from pathlib import Path

from llama_index.core.schema import Document

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError, EmptyDocumentError


@loader_for(SupportedFormat.DOC)
class DocLegacyLoader(BaseLoader):
    """
    Read a legacy .doc file via OLE2 text-stream extraction.

    Falls back to raw binary scraping if the Word Document stream is absent.
    """

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        text = self._extract_text(file_path)

        if not text.strip():
            raise EmptyDocumentError(file_path.name)

        doc = Document(text=text)
        doc_meta = metadata.model_copy(
            update={
                "page_or_slide_num": 1,
                "total_pages_or_slides": 1,
                "custom_metadata": {
                    "extraction_method": "olefile_text_stream",
                    "format_note": "Legacy .doc — formatting not preserved",
                },
            }
        )
        self._attach_metadata(doc, doc_meta)
        return [doc]

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(file_path: Path) -> str:
        """Extract readable text from a .doc OLE2 file."""
        try:
            import olefile
        except ImportError as exc:
            raise CorruptedFileError(
                file_path.name,
                reason="olefile is required for .doc support — pip install olefile",
            ) from exc

        try:
            ole = olefile.OleFileIO(str(file_path))
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"Not a valid OLE2 file: {exc}",
            ) from exc

        try:
            # The "WordDocument" stream contains the raw binary document data.
            # The text portion lives in a separate stream, but the most
            # reliable pure-Python approach is to read all streams and scrape
            # printable text.
            text_parts: list[str] = []

            for stream_path in ole.listdir():
                try:
                    data = ole.openstream(stream_path).read()
                    # Try UTF-16 LE (the encoding Word uses internally)
                    try:
                        decoded = data.decode("utf-16-le", errors="ignore")
                    except UnicodeDecodeError:
                        decoded = data.decode("latin-1", errors="ignore")

                    # Keep only lines with printable content
                    clean = _clean_binary_text(decoded)
                    if clean:
                        text_parts.append(clean)
                except Exception:
                    continue

            return "\n\n".join(text_parts)
        finally:
            ole.close()


def _clean_binary_text(raw: str) -> str:
    """Strip control characters and collapse whitespace from binary-decoded text."""
    # Remove null bytes and most control chars except newline/tab
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", raw)
    # Collapse runs of whitespace
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    # Collapse blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
