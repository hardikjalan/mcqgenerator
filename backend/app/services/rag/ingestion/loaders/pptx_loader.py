"""
pptx_loader.py
==============
Loader for modern PowerPoint files (.pptx — Office Open XML).

Uses LlamaIndex's ``PptxReader`` which delegates to ``python-pptx``.
Each slide becomes a separate ``Document`` with slide number metadata.
Speaker notes are included in the slide text when present.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import Document
from llama_index.readers.file import PptxReader

from app.services.rag.schemas import SupportedFormat, StandardDocumentMetadata
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import CorruptedFileError, EmptyDocumentError


@loader_for(SupportedFormat.PPTX)
class PptxLoader(BaseLoader):
    """Read a .pptx file and return one Document per slide."""

    def __init__(self) -> None:
        self._reader = PptxReader()

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        try:
            raw_docs: list[Document] = self._reader.load_data(file_path)
        except Exception as exc:
            raise CorruptedFileError(
                file_path.name,
                reason=f"python-pptx could not read this file: {exc}",
            ) from exc

        if not raw_docs or all(not doc.text.strip() for doc in raw_docs):
            raise EmptyDocumentError(file_path.name)

        # PptxReader may return one doc per slide or a single doc with all
        # slides concatenated — handle both cases.
        total_slides = len(raw_docs)
        result: list[Document] = []

        for idx, doc in enumerate(raw_docs):
            slide_num = idx + 1
            slide_meta = metadata.model_copy(
                update={
                    "page_or_slide_num": slide_num,
                    "total_pages_or_slides": total_slides,
                    "custom_metadata": {
                        "slide_number": slide_num,
                    },
                }
            )
            self._attach_metadata(doc, slide_meta)
            result.append(doc)

        return result
