"""
pipeline.py
===========
Download-and-extract pipeline: turns a signed-URL file reference into plain text.

Moved verbatim out of main.py so routes stay thin and the pipeline can be
reused by future endpoints (regeneration, student-submitted material) without
importing the FastAPI app.

Processing flow (visible in logs):
    → [DOWNLOAD] file.pdf → OK (45,231 bytes)
    → [EXTRACT]  file.pdf → 3,201 chars

All pipeline errors are caught here; only user-safe messages surface. Internal
details are logged but never returned to the client.
"""

import os
import tempfile

import httpx

from app.core.config import SUPPORTED_EXTENSIONS
from app.core.exceptions import DocumentProcessingError, UnsupportedFileTypeError
from app.core.logger import get_logger, is_debug_mode
from app.schemas.assessment import FileItem
from app.services.extraction.extractors.docx_extractor import DocxExtractor
from app.services.extraction.extractors.ocr_extractor import OCRExtractor
from app.services.extraction.extractors.pdf_extractor import PDFExtractor
from app.services.extraction.extractors.pptx_extractor import PptxExtractor

logger = get_logger(__name__)


def get_extractor_for(ext: str, file_path: str):
    """
    Return the correct extractor for the given extension.

    Raises
    ------
    UnsupportedFileTypeError
        If the extension is not in SUPPORTED_EXTENSIONS.
    """
    ext = ext.lower()
    if ext == "pdf":
        return PDFExtractor(file_path)
    elif ext == "docx":
        return DocxExtractor(file_path)
    elif ext in ("pptx", "ppt"):
        return PptxExtractor(file_path)
    elif ext in ("png", "jpg", "jpeg"):
        return OCRExtractor(file_path)
    raise UnsupportedFileTypeError(ext)


def download_and_extract(file: FileItem) -> dict:
    """
    Download a file from its signed URL and extract its text.

    Returns a result dict with keys: name, status, text, error.
    All pipeline errors are caught here; only user-safe messages surface.

    Log flow:
        [DOWNLOAD] filename.pdf → OK (45,231 bytes)
        [EXTRACT]  filename.pdf → 3,201 chars
    """
    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else ""

    # ── Validate extension before downloading ─────────────────────────────────
    if ext not in SUPPORTED_EXTENSIONS:
        logger.warning("[DOWNLOAD] Unsupported type '.%s': %s", ext, file.name)
        return {
            "name": file.name,
            "status": "error",
            "error": f"The file type '.{ext}' is not supported. Supported: PDF, DOCX, PPTX, PNG, JPG, JPEG.",
            "text": "",
        }

    # ── Download ──────────────────────────────────────────────────────────────
    try:
        response = httpx.get(file.signedUrl, timeout=30, follow_redirects=True)
        response.raise_for_status()
        logger.info("[DOWNLOAD] %s — OK (%d bytes)", file.name, len(response.content))
    except httpx.TimeoutException:
        logger.warning("[DOWNLOAD] %s — timeout", file.name)
        return {
            "name": file.name,
            "status": "error",
            "error": "The file download timed out. Please try again.",
            "text": "",
        }
    except httpx.HTTPStatusError as e:
        logger.warning("[DOWNLOAD] %s — HTTP %d", file.name, e.response.status_code)
        return {
            "name": file.name,
            "status": "error",
            "error": "The file could not be downloaded (server returned an error). Please re-upload.",
            "text": "",
        }
    except Exception as e:
        logger.error("[DOWNLOAD] %s — unexpected error: %s", file.name, e, exc_info=is_debug_mode())
        return {
            "name": file.name,
            "status": "error",
            "error": "The file could not be downloaded. Please check your connection and try again.",
            "text": "",
        }

    # ── Write to temp file & extract ──────────────────────────────────────────
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as tmp:
            tmp.write(response.content)
            tmp_path = tmp.name

        extractor = get_extractor_for(ext, tmp_path)
        text = extractor.extract_text()
        logger.info("[EXTRACT] %s — %d chars", file.name, len(text))
        return {"name": file.name, "status": "success", "text": text, "error": None}

    except DocumentProcessingError as e:
        # Structured pipeline error — log internal detail once, return user message
        logger.error("[EXTRACT] %s — %s", file.name, e.message)
        return {
            "name": file.name,
            "status": "error",
            "error": e.user_message,
            "text": "",
        }
    except Exception as e:
        logger.error("[EXTRACT] %s — unexpected: %s", file.name, e, exc_info=True)
        return {
            "name": file.name,
            "status": "error",
            "error": "An unexpected error occurred while processing the file.",
            "text": "",
        }
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError as cleanup_err:
                logger.debug("Could not delete temp file %s: %s", tmp_path, cleanup_err)
