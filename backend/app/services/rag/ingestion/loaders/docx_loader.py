"""
docx_loader.py
==============
Loader for modern Word documents (.docx — Office Open XML).

Uses ``python-docx`` directly to iterate over paragraphs and tables,
preserving heading styles as Markdown markers (``#``, ``##``, ``###``)
and tables as Markdown grids where available and accurately extractable.

The entire document is returned as a single ``Document`` with structural
formatting embedded in the text.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document as DocxDocument
from llama_index.core.schema import Document

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError


# ── Heading style name → Markdown prefix mapping ────────────────────────────

_HEADING_PREFIX: dict[str, str] = {
    "Heading 1": "# ",
    "Heading 2": "## ",
    "Heading 3": "### ",
    "Heading 4": "#### ",
    "Heading 5": "##### ",
    "Heading 6": "###### ",
    "Title": "# ",
    "Subtitle": "## ",
}


def _table_to_markdown(table) -> str:
    """Convert a ``python-docx`` table to a Markdown grid.

    Returns an empty string if the table has no rows or columns.
    """
    rows = table.rows
    if not rows:
        return ""

    lines: list[str] = []
    for r_idx, row in enumerate(rows):
        cells = [cell.text.replace("|", "\\|").strip() for cell in row.cells]
        lines.append("| " + " | ".join(cells) + " |")
        if r_idx == 0:
            # Separator row after header
            lines.append("| " + " | ".join("---" for _ in cells) + " |")

    return "\n".join(lines)


@loader_for(SupportedFormat.DOCX)
class DocxLoader(BaseLoader):
    """Read a .docx file preserving headings and tables as Markdown.

    Iterates through the document body using ``python-docx`` to read
    paragraphs (with their style names) and tables, producing a single
    ``Document`` with structural formatting where available.
    """

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        try:
            docx_doc = DocxDocument(str(file_path))
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"python-docx could not read this file: {exc}",
            ) from exc

        parts: list[str] = []

        # python-docx exposes body elements in document order, which
        # interleaves paragraphs and tables.  We iterate over the
        # underlying XML children to preserve the correct ordering.
        from docx.oxml.ns import qn

        body = docx_doc.element.body
        # Build a lookup for table XML elements → table objects
        table_elements = {tbl._element: tbl for tbl in docx_doc.tables}

        for child in body:
            tag = child.tag

            if tag == qn("w:p"):
                # It's a paragraph — find the matching Paragraph object
                para = None
                for p in docx_doc.paragraphs:
                    if p._element is child:
                        para = p
                        break
                if para is None or not para.text.strip():
                    continue

                prefix = _HEADING_PREFIX.get(para.style.name, "")
                parts.append(f"{prefix}{para.text}")

            elif tag == qn("w:tbl"):
                # It's a table — find the matching Table object
                tbl_obj = table_elements.get(child)
                if tbl_obj is not None:
                    md_table = _table_to_markdown(tbl_obj)
                    if md_table:
                        parts.append(md_table)

        text = "\n\n".join(parts)

        doc = Document(text=text)
        doc_meta = metadata.model_copy(
            update={
                "page_or_slide_num": 1,
                "total_pages_or_slides": 1,
                "custom_metadata": {
                    "section_index": 0,
                },
            }
        )
        self._attach_metadata(doc, doc_meta)

        return self.clean_and_validate([doc], file_name=file_path.name)
