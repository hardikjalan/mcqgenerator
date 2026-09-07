"""
ppt_loader.py
=============
Loader for legacy PowerPoint files (.ppt — OLE2 binary format).

``python-pptx`` only supports the modern XML-based ``.pptx`` format, so binary
decks are read with ``olefile`` and the shared salvage filter — see
``ingestion/salvage.py`` for why recovery is heuristic and how the noise is
kept out.

Only the ``PowerPoint Document`` stream is read. The other streams in the
container hold metadata, pictures and object headers; scanning them all was
the original source of the mojibake this loader used to emit.

Limitations
-----------
- Formatting, images and transitions are lost.
- Slide boundaries are not recoverable, so the deck becomes one Document.
- Non-Latin scripts are not salvaged (see ``salvage.py``).
- Password-protected files raise ``CorruptedFileError``.

Re-saving the deck as .pptx avoids every one of these and gives a complete,
per-slide extraction — which is what the error messages here tell the user.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import Document

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError
from app.services.rag.ingestion.salvage import is_substantial, salvage_readable

_TEXT_STREAM = "powerpoint document"


@loader_for(SupportedFormat.PPT)
class PptLegacyLoader(BaseLoader):
    """Read a legacy .ppt by salvaging text from its OLE2 text stream."""

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        text = self._extract_text(file_path)

        doc = Document(text=text)
        doc_meta = metadata.model_copy(
            update={
                "page_or_slide_num": 1,
                "total_pages_or_slides": 1,
                "custom_metadata": {
                    "extraction_method": "ole2_salvage",
                    "format_note": "Legacy .ppt — slide boundaries not recoverable",
                },
            }
        )
        self._attach_metadata(doc, doc_meta)
        return self.clean_and_validate([doc], file_name=file_path.name)

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _extract_text(file_path: Path) -> str:
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
            raw = _read_stream(ole, _TEXT_STREAM)
        finally:
            ole.close()

        if raw is None:
            raise CorruptedFileError(
                file_path.name,
                reason="No 'PowerPoint Document' stream found",
            )

        text = salvage_readable(raw)

        if not is_substantial(text):
            raise CorruptedFileError(
                file_path.name,
                reason=(
                    "Only unreadable binary content could be recovered. Open it "
                    "in PowerPoint and save it as .pptx, then upload that."
                ),
            )

        return text


def _read_stream(ole, name: str) -> bytes | None:
    """Return the raw bytes of a named OLE2 stream, or None if absent."""
    for stream_path in ole.listdir():
        if stream_path and stream_path[-1].lower() == name:
            return ole.openstream(stream_path).read()
    return None
