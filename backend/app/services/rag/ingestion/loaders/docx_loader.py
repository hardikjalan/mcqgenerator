"""
docx_loader.py
==============
Loader for modern Word documents (.docx — Office Open XML).

Uses LlamaIndex's ``DocxReader`` which delegates to ``python-docx``.
The entire document body is returned as a single ``Document``.  Heading
hierarchy and table content are preserved in the raw text.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import Document
from llama_index.readers.file import DocxReader

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError


@loader_for(SupportedFormat.DOCX)
class DocxLoader(BaseLoader):
    """Read a .docx file and return its content as Document(s)."""

    def __init__(self) -> None:
        super().__init__()
        self._reader = DocxReader()

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        try:
            raw_docs: list[Document] = self._reader.load_data(file_path)
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"python-docx could not read this file: {exc}",
            ) from exc

        result: list[Document] = []
        total = len(raw_docs)

        for idx, doc in enumerate(raw_docs):
            section_meta = metadata.model_copy(
                update={
                    "page_or_slide_num": idx + 1,
                    "total_pages_or_slides": total,
                    "custom_metadata": {
                        "section_index": idx,
                    },
                }
            )
            self._attach_metadata(doc, section_meta)
            result.append(doc)

        return self.clean_and_validate(result, file_name=file_path.name)
