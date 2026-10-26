"""
pdf_loader.py
=============
Loader for PDF files (.pdf).

Uses ``pymupdf4llm`` (backed by PyMuPDF) to produce Markdown-formatted
text that preserves headings, tables, formulas, and paragraph boundaries
where available and accurately extractable.  Each physical page becomes
a separate ``Document`` with its page number preserved in metadata.

Falls back gracefully: if ``pymupdf4llm`` cannot extract text for a page,
raw PyMuPDF text extraction (``page.get_text()``) is attempted before
raising ``CorruptedFileError``.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf
import pymupdf4llm
from llama_index.core.schema import Document

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError
from app.services.rag.ingestion.vision import read_image


@loader_for(SupportedFormat.PDF)
class PDFLoader(BaseLoader):
    """Read a PDF file and return one Document per page.

    Uses ``pymupdf4llm.to_markdown(page_chunks=True)`` to extract
    structure-aware Markdown text.  Headings, tables, formulas, and
    paragraph boundaries are preserved where the PDF layout allows
    accurate extraction.
    """

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        try:
            pdf_doc = pymupdf.open(file_path)
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"PyMuPDF could not open this PDF: {exc}",
            ) from exc

        try:
            if len(pdf_doc) > 100:
                raise ValueError("PDF exceeds the 100-page processing limit.")
            chunks = pymupdf4llm.to_markdown(pdf_doc, page_chunks=True)
        except Exception as exc:
            pdf_doc.close()
            raise CorruptedFileError(
                file_path.name,
                reason=f"pymupdf4llm could not convert this PDF: {exc}",
            ) from exc

        total_pages = len(chunks)
        result: list[Document] = []
        ocr_pages = 0

        for idx, chunk in enumerate(chunks):
            page_num = idx + 1
            text = chunk.get("text", "")

            # Fallback: if pymupdf4llm returned blank text for this page,
            # try raw PyMuPDF text extraction.
            if not text.strip() and idx < len(pdf_doc):
                text = pdf_doc[idx].get_text("text") or ""

            extraction_method = "text"
            if not text.strip() or (len(text.strip()) < 80 and pdf_doc[idx].get_images()):
                ocr_pages += 1
                if ocr_pages > 20:
                    pdf_doc.close()
                    raise ValueError("A request can OCR up to 20 scanned PDF pages. Split this file.")
                try:
                    image = pdf_doc[idx].get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5))
                    text = read_image(image.tobytes("png"), "image/png")
                    extraction_method = "vision_ocr"
                except Exception:
                    pdf_doc.close()
                    raise

            doc = Document(text=text)

            page_meta = metadata.model_copy(
                update={
                    "page_or_slide_num": page_num,
                    "total_pages_or_slides": total_pages,
                    "custom_metadata": {
                        "page_label": str(page_num),
                        "extraction_method": extraction_method,
                    },
                }
            )
            self._attach_metadata(doc, page_meta)
            result.append(doc)

        pdf_doc.close()
        return self.clean_and_validate(result, file_name=file_path.name)
