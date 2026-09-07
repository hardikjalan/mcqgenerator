"""
image_loader.py
===============
Loader for standalone images (.png, .jpg, .webp, .gif, .bmp, .tiff).

An image has no text layer to read, so this loader is entirely OCR. It
registers for every image format, which means an uploaded PNG reaches a loader
even when OCR is switched off — and that is the point. Without it, detection
would fail first and the user would be told their PNG is an unsupported file
type, immediately after an upload widget accepted it. Getting as far as
``OCRUnavailableError`` lets us say the true thing instead: text recognition
isn't switched on.
"""

from __future__ import annotations

from pathlib import Path

from llama_index.core.schema import Document

from app.services.rag.schemas import (
    IMAGE_MIME_TYPES,
    StandardDocumentMetadata,
    SupportedFormat,
)
from app.services.rag.ingestion.base import BaseLoader
from app.services.rag.ingestion.registry import loader_for
from app.services.rag.ingestion.exceptions import EmptyDocumentError
from app.services.rag.ingestion import ocr as ocr_module
from app.services.rag.ingestion.ocr import OCRUnavailableError


@loader_for(SupportedFormat.PNG)
@loader_for(SupportedFormat.JPG)
@loader_for(SupportedFormat.WEBP)
@loader_for(SupportedFormat.GIF)
@loader_for(SupportedFormat.BMP)
@loader_for(SupportedFormat.TIFF)
class ImageLoader(BaseLoader):
    """Read the text in an image via the configured OCR provider."""

    def load(self, file_path: Path, metadata: StandardDocumentMetadata) -> list[Document]:
        # Resolved per call, not per instance: loaders are constructed once at
        # import time, long before the environment is necessarily settled.
        provider = ocr_module.get_provider()
        if provider is None:
            raise OCRUnavailableError()

        fmt = SupportedFormat(metadata.file_type)
        text = provider.extract_text(
            file_path.read_bytes(),
            mime_type=IMAGE_MIME_TYPES.get(fmt, "image/png"),
            file_name=file_path.name,
        )

        if not text.strip():
            # A provider that reads nothing is not a provider that failed —
            # the image genuinely had no text in it.
            raise EmptyDocumentError(file_path.name)

        doc = Document(text=text)
        doc_meta = metadata.model_copy(
            update={
                "page_or_slide_num": 1,
                "total_pages_or_slides": 1,
                "custom_metadata": {
                    "extraction_method": f"ocr:{provider.name}",
                },
            }
        )
        self._attach_metadata(doc, doc_meta)
        return self.clean_and_validate([doc], file_name=file_path.name)
