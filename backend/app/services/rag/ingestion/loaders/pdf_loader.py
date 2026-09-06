"""
pdf_loader.py
=============
Loader for PDF files (.pdf).

Uses LlamaIndex's ``PDFReader`` which delegates to ``pypdf``.  Each page
becomes a separate ``Document`` with its page number preserved in metadata.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import Document
from llama_index.readers.file import PDFReader

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError


@loader_for(SupportedFormat.PDF)
class PDFLoader(BaseLoader):
    """Read a PDF file and return one Document per page."""

    def __init__(self) -> None:
        super().__init__()
        self._reader = PDFReader(return_full_document=False)

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        try:
            raw_docs: list[Document] = self._reader.load_data(file_path)
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"pypdf could not read this PDF: {exc}",
            ) from exc

        total_pages = len(raw_docs)
        result: list[Document] = []

        for idx, doc in enumerate(raw_docs):
            page_num = idx + 1
            page_meta = metadata.model_copy(
                update={
                    "page_or_slide_num": page_num,
                    "total_pages_or_slides": total_pages,
                    "custom_metadata": {
                        "page_label": str(page_num),
                    },
                }
            )
            self._attach_metadata(doc, page_meta)
            result.append(doc)

        return self.clean_and_validate(result, file_name=file_path.name)
