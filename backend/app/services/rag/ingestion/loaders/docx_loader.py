"""
docx_loader.py
==============
Loader for modern Word documents (.docx — Office Open XML).

Uses ``python-docx`` directly rather than LlamaIndex's ``DocxReader``.
``DocxReader`` delegates to ``docx2txt``, which is a separate dependency that
is not in requirements.txt — with only ``python-docx`` installed it raises
"docx2txt is required to read Microsoft Word files" and every .docx upload
fails. Reading the document ourselves removes that dependency and gives us
table text, which ``docx2txt`` drops.

A .docx has no page breaks to split on — pagination happens at render time,
not in the file — so the body is returned as a single ``Document``.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import Document

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError


@loader_for(SupportedFormat.DOCX)
class DocxLoader(BaseLoader):
    """Read a .docx file and return its body as a single Document."""

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        try:
            import docx  # python-docx
        except ImportError as exc:  # pragma: no cover - declared in requirements
            raise CorruptedFileError(
                file_path.name,
                reason="python-docx is not installed",
            ) from exc

        try:
            source = docx.Document(str(file_path))
            blocks = self._read_blocks(source)
        except CorruptedFileError:
            raise
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"python-docx could not read this file: {exc}",
            ) from exc

        doc = Document(text="\n\n".join(blocks))
        doc_meta = metadata.model_copy(
            update={
                "page_or_slide_num": 1,
                "total_pages_or_slides": 1,
                "custom_metadata": {
                    "paragraph_count": len(source.paragraphs),
                    "table_count": len(source.tables),
                },
            }
        )
        self._attach_metadata(doc, doc_meta)
        return self.clean_and_validate([doc], file_name=file_path.name)

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _read_blocks(source) -> list[str]:
        """Collect paragraph text, then table text.

        Headings are kept verbatim — their style carries the outline level,
        which the chunking layer can use later, but the text itself is what
        matters here. Empty paragraphs are dropped so the cleaner is not
        left collapsing dozens of blank lines.
        """
        blocks = [p.text.strip() for p in source.paragraphs if p.text.strip()]

        for table in source.tables:
            for row in table.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    # Tab-separated keeps the row readable as one line without
                    # inventing markup the source did not have.
                    blocks.append("\t".join(cells))

        return blocks
