"""
pipeline.py
===========
Download-and-extract pipeline: turns a signed-URL file reference into
LlamaIndex ``Document`` objects.

Parsing is LlamaIndex's job now — the hand-rolled loaders and per-format
extractors are gone. What remains here is everything the readers do *not* do:
downloading the signed URL, validating the extension, mapping reader failures
onto the ``DocumentProcessingError`` hierarchy, and OCR'ing scanned PDFs.

``Document`` is the unit that leaves this module. The route flattens it to
plain text for the current response shape; the RAG pipeline will consume the
Documents directly, which is the reason for the switch.

Reader map
----------
====== ==================== ==========================================
ext    reader               notes
====== ==================== ==========================================
pdf    ``PyMuPDFReader``    text layer only — see ``ocr_fallback``
docx   ``DocxReader``       backed by docx2txt, not python-docx
pptx   ``PptxReader``       backed by python-pptx
image  *none*               ``ImageReader``'s default path pulls torch +
                            transformers, so Gemini OCR handles these
====== ==================== ==========================================

Processing flow (visible in logs):
    → [DOWNLOAD] file.pdf → OK (45,231 bytes)
    → [EXTRACT]  file.pdf → 12 doc(s), 3,201 chars

All pipeline errors are caught here; only user-safe messages surface. Internal
details are logged but never returned to the client.
"""

import os
import tempfile
from pathlib import Path

import httpx
from llama_index.core.schema import Document
from llama_index.readers.file import DocxReader, PptxReader, PyMuPDFReader

from app.core.config import DEBUG_OUTPUT_PATH, SUPPORTED_EXTENSIONS
from app.core.exceptions import (
    CorruptedFileError,
    DocumentProcessingError,
    UnsupportedFileTypeError,
)
from app.core.logger import get_logger, is_debug_mode
from app.schemas.assessment import FileItem
from app.services.extraction.extractors.gemini_ocr import extract_text_from_image
from app.services.extraction.ocr_fallback import looks_scanned, ocr_scanned_pages

logger = get_logger(__name__)

MIME_TYPE_MAP = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
}


# ── Per-format readers ────────────────────────────────────────────────────────

def _read_pdf(file_path: str) -> list[Document]:
    """
    Read a PDF's text layer, falling back to OCR when that layer is thin.

    ``PyMuPDFReader`` yields one Document per page. A scanned PDF yields the
    right number of empty ones, which is why the character count — not the
    Document count — decides whether OCR runs.
    """
    documents = PyMuPDFReader().load_data(file_path=Path(file_path))

    text_chars = sum(len(d.text.strip()) for d in documents)
    if not looks_scanned(text_chars, len(documents)):
        return documents

    logger.info(
        "[EXTRACT] Thin text layer (%d chars over %d page(s)) — trying OCR",
        text_chars, len(documents),
    )
    ocr_text = ocr_scanned_pages(file_path)
    if ocr_text:
        documents.append(
            Document(text=ocr_text, metadata={"source": "gemini_ocr", "file_path": file_path})
        )
    return documents


def _read_image(file_path: str, ext: str) -> list[Document]:
    """
    OCR an image straight through Gemini.

    LlamaIndex's ``ImageReader`` is deliberately not used: its default parser
    needs torch + transformers + sentencepiece, and its lighter path is bare
    pytesseract — worse than the retry-and-fallback ladder in ``gemini_ocr``.
    """
    with open(file_path, "rb") as f:
        image_bytes = f.read()

    text = extract_text_from_image(image_bytes, mime_type=MIME_TYPE_MAP.get(ext, "image/jpeg"))
    return [
        Document(
            text=text or "",
            metadata={"source": "gemini_ocr", "file_path": file_path},
        )
    ]


def read_documents(ext: str, file_path: str) -> list[Document]:
    """
    Parse a file into LlamaIndex Documents using the reader for its extension.

    Raises
    ------
    UnsupportedFileTypeError
        If the extension has no reader.
    CorruptedFileError
        If the reader cannot parse the file.
    DocumentProcessingError
        Propagated unchanged from the OCR layer.
    """
    ext = ext.lower()

    try:
        if ext == "pdf":
            return _read_pdf(file_path)
        if ext == "docx":
            return DocxReader().load_data(file=Path(file_path))
        if ext == "pptx":
            # extract_images would caption via an LLM; context consolidation
            # would call one per slide. Both off — this stage is parsing only.
            return PptxReader(
                extract_images=False,
                context_consolidation_with_llm=False,
            ).load_data(file=Path(file_path))
        if ext in MIME_TYPE_MAP:
            return _read_image(file_path, ext)
    except DocumentProcessingError:
        # Already structured (OCR errors) — let it through untouched.
        raise
    except Exception as e:
        # Readers raise whatever their backing library raises. Everything that
        # gets here means "this file could not be parsed".
        logger.debug("[EXTRACT] Reader failed for .%s: %s", ext, e)
        raise CorruptedFileError(file_path, str(e)) from e

    raise UnsupportedFileTypeError(ext)


# ── Download + extract ────────────────────────────────────────────────────────

def download_and_extract(file: FileItem) -> dict:
    """
    Download a file from its signed URL and extract its text.

    Returns a result dict with keys: name, status, text, documents, error.
    ``documents`` carries the LlamaIndex Documents for downstream indexing;
    ``text`` is the flattened form the current API response uses.

    All pipeline errors are caught here; only user-safe messages surface.

    Log flow:
        [DOWNLOAD] filename.pdf → OK (45,231 bytes)
        [EXTRACT]  filename.pdf → 12 doc(s), 3,201 chars
    """
    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""

    # ── Validate extension before downloading ─────────────────────────────────
    if ext not in SUPPORTED_EXTENSIONS:
        logger.warning("[DOWNLOAD] Unsupported type '.%s': %s", ext, file.name)
        return _failure(
            file.name,
            f"The file type '.{ext}' is not supported. Supported: PDF, DOCX, PPTX, PNG, JPG, JPEG.",
        )

    # ── Download ──────────────────────────────────────────────────────────────
    try:
        response = httpx.get(file.signedUrl, timeout=30, follow_redirects=True)
        response.raise_for_status()
        logger.info("[DOWNLOAD] %s — OK (%d bytes)", file.name, len(response.content))
    except httpx.TimeoutException:
        logger.warning("[DOWNLOAD] %s — timeout", file.name)
        return _failure(file.name, "The file download timed out. Please try again.")
    except httpx.HTTPStatusError as e:
        logger.warning("[DOWNLOAD] %s — HTTP %d", file.name, e.response.status_code)
        return _failure(
            file.name,
            "The file could not be downloaded (server returned an error). Please re-upload.",
        )
    except Exception as e:
        logger.error("[DOWNLOAD] %s — unexpected error: %s", file.name, e, exc_info=is_debug_mode())
        return _failure(
            file.name,
            "The file could not be downloaded. Please check your connection and try again.",
        )

    # An empty download parses to an empty Document rather than failing, which
    # would surface as a silent success. Catch it here instead.
    if not response.content:
        logger.warning("[DOWNLOAD] %s — empty file (0 bytes)", file.name)
        return _failure(
            file.name,
            "The file appears to be empty. Please check the file and upload it again.",
        )

    # ── Write to temp file & extract ──────────────────────────────────────────
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        documents = read_documents(ext, tmp_path)
        text = "\n".join(d.text.strip() for d in documents if d.text.strip()).strip()

        logger.info("[EXTRACT] %s — %d doc(s), %d chars", file.name, len(documents), len(text))
        _write_debug_file(file.name, text)

        return {
            "name": file.name,
            "status": "success",
            "text": text,
            "documents": documents,
            "error": None,
        }

    except DocumentProcessingError as e:
        # Structured pipeline error — log internal detail once, return user message
        logger.error("[EXTRACT] %s — %s", file.name, e.message)
        return _failure(file.name, e.user_message)
    except Exception as e:
        logger.error("[EXTRACT] %s — unexpected: %s", file.name, e, exc_info=True)
        return _failure(file.name, "An unexpected error occurred while processing the file.")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as cleanup_err:
                logger.debug("Could not delete temp file %s: %s", tmp_path, cleanup_err)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _failure(name: str, message: str) -> dict:
    """Build the error-shaped result dict. Keys match the success shape."""
    return {"name": name, "status": "error", "text": "", "documents": [], "error": message}


def _write_debug_file(name: str, text: str) -> None:
    """
    Dump the last extraction to disk when LOG_LEVEL=DEBUG.

    Every extractor used to do this itself; there is one extraction path now,
    so it lives here.
    """
    if not is_debug_mode():
        return
    try:
        with open(DEBUG_OUTPUT_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        logger.debug("[EXTRACT] Debug file saved for %s: %s", name, os.path.abspath(DEBUG_OUTPUT_PATH))
    except OSError as e:
        logger.debug("[EXTRACT] Could not write debug file: %s", e)
