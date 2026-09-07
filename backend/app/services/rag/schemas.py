"""
schemas.py
==========
Shared types for the RAG pipeline.

Every layer (ingestion → parsing → chunking → retrieval → generation) imports
from here so the contract between layers is defined once.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ── Supported document formats ────────────────────────────────────────────────

class SupportedFormat(str, Enum):
    """File formats the ingestion layer can process.

    The image formats require a configured OCR provider. Without one they are
    still *detected* — so the user is told text recognition is switched off,
    rather than that their PNG is an unknown file type.
    """

    PDF = "pdf"
    DOCX = "docx"
    DOC = "doc"
    PPTX = "pptx"
    PPT = "ppt"
    PNG = "png"
    JPG = "jpg"
    WEBP = "webp"
    GIF = "gif"
    BMP = "bmp"
    TIFF = "tiff"


IMAGE_FORMATS = frozenset({
    SupportedFormat.PNG,
    SupportedFormat.JPG,
    SupportedFormat.WEBP,
    SupportedFormat.GIF,
    SupportedFormat.BMP,
    SupportedFormat.TIFF,
})

# MIME type per image format — OCR providers need it alongside the bytes.
IMAGE_MIME_TYPES = {
    SupportedFormat.PNG: "image/png",
    SupportedFormat.JPG: "image/jpeg",
    SupportedFormat.WEBP: "image/webp",
    SupportedFormat.GIF: "image/gif",
    SupportedFormat.BMP: "image/bmp",
    SupportedFormat.TIFF: "image/tiff",
}


# ── Metadata attached to every ingested Document ─────────────────────────────

class StandardDocumentMetadata(BaseModel):
    """
    Uniform metadata that every loader must attach to each Document it emits.

    Layer 2 (Parsing & Cleaning) relies on these fields being present and
    consistently named.  Loaders may add extra keys to ``custom_metadata``
    without breaking the contract.
    """

    file_name: str
    file_type: SupportedFormat
    file_size_bytes: int
    source_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    page_or_slide_num: int | None = None
    total_pages_or_slides: int | None = None
    ingested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    custom_metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(use_enum_values=True)


# ── Output of Layer 1 (Ingestion) ────────────────────────────────────────────

class IngestionResult(BaseModel):
    """
    The complete output of ingesting a single file.

    ``documents`` contains the raw LlamaIndex ``Document`` objects — one per
    page / slide / section — ready for Layer 2.  They are typed as ``Any``
    here because Pydantic cannot natively serialise LlamaIndex objects; the
    actual runtime type is ``llama_index.core.schema.Document``.
    """

    source_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_name: str
    file_type: SupportedFormat
    total_units: int = 0          # pages, slides, or sections
    documents: list[Any] = Field(default_factory=list)
    raw_char_count: int = 0
    errors: list[str] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True, arbitrary_types_allowed=True)
