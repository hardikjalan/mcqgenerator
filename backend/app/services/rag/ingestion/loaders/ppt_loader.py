"""
ppt_loader.py
=============
Loader for legacy PowerPoint files (.ppt — OLE2 binary format).

``python-pptx`` only supports the modern XML-based ``.pptx`` format.  For
binary ``.ppt`` files we use ``olefile`` to read the OLE2 compound document
and extract text from the ``PowerPoint Document`` stream.

This provides a pure-Python fallback that works on Windows without requiring
external tools like LibreOffice.

Limitations
-----------
- Only raw text content is extracted — formatting, images, and transitions
  are lost.
- Slide boundaries are approximated from the binary stream.
- Password-protected files raise ``CorruptedFileError``.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import Document

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError


@loader_for(SupportedFormat.PPT)
class PptLegacyLoader(BaseLoader):
    """
    Read a legacy .ppt file via OLE2 text-stream extraction.

    The entire presentation is returned as a single Document since slide
    boundaries are unreliable in the binary format.

    Text cleaning is handled centrally by ``BaseLoader.clean_and_validate()``.
    """

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        text = self._extract_text(file_path)

        doc = Document(text=text)
        doc_meta = metadata.model_copy(
            update={
                "page_or_slide_num": 1,
                "total_pages_or_slides": 1,
                "custom_metadata": {
                    "extraction_method": "olefile_text_stream",
                    "format_note": "Legacy .ppt — slide boundaries approximate",
                },
            }
        )
        self._attach_metadata(doc, doc_meta)
        return self.clean_and_validate([doc], file_name=file_path.name)

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(file_path: Path) -> str:
        """Extract readable text from a .ppt OLE2 file."""
        try:
            import olefile
        except ImportError as exc:
            raise CorruptedFileError(
                file_path.name,
                reason="olefile is required for .ppt support — pip install olefile",
            ) from exc

        try:
            ole = olefile.OleFileIO(str(file_path))
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"Not a valid OLE2 file: {exc}",
            ) from exc

        try:
            text_parts: list[str] = []

            for stream_path in ole.listdir():
                try:
                    data = ole.openstream(stream_path).read()
                    # PowerPoint stores text as UTF-16 LE
                    try:
                        decoded = data.decode("utf-16-le", errors="ignore")
                    except UnicodeDecodeError:
                        decoded = data.decode("latin-1", errors="ignore")

                    if decoded.strip():
                        text_parts.append(decoded)
                except Exception:
                    continue

            return "\n\n".join(text_parts)
        finally:
            ole.close()
