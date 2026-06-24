"""
main.py
=======
FastAPI application entry point for the MCQ Generator backend.

Processing flow (visible in logs):
    → Request received
    → [DOWNLOAD] file.pdf
    → [EXTRACT]  file.pdf
    → Response

All pipeline errors (validation, loading, extraction) are caught here and
converted to frontend-safe JSON responses. Internal details are logged but
never exposed to the client.
"""

import os
import sys
import tempfile
import httpx

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Optional

# Ensure backend root is importable
sys.path.insert(0, os.path.dirname(__file__))

from extractors.pdf_extractor import PDFExtractor
from extractors.docx_extractor import DocxExtractor
from extractors.pptx_extractor import PptxExtractor
from extractors.ocr_extractor import OCRExtractor
from exceptions import (
    DocumentProcessingError,
    FileValidationError,
    UnsupportedFileTypeError,
)
from responses import success_response, error_response
from logger import get_logger, is_debug_mode

logger = get_logger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MCQ Generator API",
    description="Backend API for extracting text from documents and generating assessments.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handlers ─────────────────────────────────────────────────

@app.exception_handler(DocumentProcessingError)
async def document_processing_error_handler(
    request: Request, exc: DocumentProcessingError
) -> JSONResponse:
    """
    Convert any unhandled DocumentProcessingError into a frontend-safe JSON response.
    These are expected pipeline errors — logged concisely without a stack trace.
    """
    logger.error(
        "[ERROR] %s %s — %s",
        request.method, request.url.path, exc.message,
    )
    return error_response(exc.user_message, status_code=exc.http_status)


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for any unexpected error — always logs full trace, never leaks internals."""
    logger.error(
        "[ERROR] Unexpected exception on %s %s: %s",
        request.method, request.url.path, exc,
        exc_info=True,  # Always full trace — this should never happen in normal operation
    )
    return error_response(
        "An unexpected server error occurred. Please try again later.",
        status_code=500,
    )

# ── Request schemas ───────────────────────────────────────────────────────────

class QuizConfigSchema(BaseModel):
    subjectName: str
    topicsCovered: str
    learningObjective: str
    gradeLevel: str
    questionType: str
    questionCount: int
    timeLimit: str


class FileItem(BaseModel):
    name: str        # original filename e.g. "lecture.pdf"
    signedUrl: str   # temporary Supabase signed URL to download the file
    size_bytes: int  # original File.size from the browser (bytes) — used for cumulative cap


class GenerateRequest(BaseModel):
    sourceType: str              # "upload" or "text"
    textContent: Optional[str] = None
    files: Optional[List[FileItem]] = None
    config: QuizConfigSchema

# ── Supported types ───────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = {"pdf", "docx", "pptx", "ppt", "png", "jpg", "jpeg"}

# ── Cumulative upload limit ───────────────────────────────────────────────────
# Shared with the frontend (components/faculty/types.ts → MAX_CUMULATIVE_SIZE).
# This is the single source-of-truth enforcement; the frontend check is a UX
# convenience that prevents unnecessary Supabase uploads.
MAX_CUMULATIVE_SIZE_MB = 5

# ── Helpers ───────────────────────────────────────────────────────────────────

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

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return success_response({"status": "Backend is running"})


@app.post("/generate-assessment")
def generate_assessment(payload: GenerateRequest):
    logger.info(
        "→ Request received: sourceType=%s, files=%d, config=%s/%s",
        payload.sourceType,
        len(payload.files) if payload.files else 0,
        payload.config.questionType,
        payload.config.questionCount,
    )

    extracted_sources = []

    # 1. Process uploaded files
    if payload.sourceType == "upload":
        if not payload.files:
            logger.warning("[ERROR] Upload request with no files")
            return error_response("No files were provided for upload processing.", status_code=400)

        # ── Cumulative size guard ─────────────────────────────────────────────
        total_bytes = sum(f.size_bytes for f in payload.files)
        total_mb = total_bytes / (1024 * 1024)
        if total_mb > MAX_CUMULATIVE_SIZE_MB:
            logger.warning(
                "[ERROR] Upload size %.2f MB exceeds %d MB limit (%d files)",
                total_mb, MAX_CUMULATIVE_SIZE_MB, len(payload.files),
            )
            return error_response(
                f"Total upload size ({total_mb:.1f} MB) exceeds the "
                f"{MAX_CUMULATIVE_SIZE_MB} MB limit. "
                f"Please reduce the number or size of your files.",
                status_code=413,
            )
        # ─────────────────────────────────────────────────────────────────────

        logger.info("Processing %d file(s) — %.2f MB total", len(payload.files), total_mb)
        for file in payload.files:
            result = download_and_extract(file)
            extracted_sources.append(result)

    # 2. Process pasted text
    elif payload.sourceType == "text":
        if not payload.textContent or not payload.textContent.strip():
            logger.warning("[ERROR] Text request with empty textContent")
            return error_response("No text content was provided.", status_code=400)
        logger.info("[EXTRACT] Text input — %d chars", len(payload.textContent))
        extracted_sources.append({
            "name": "Pasted Text",
            "status": "success",
            "text": payload.textContent,
            "error": None,
        })

    else:
        logger.warning("[ERROR] Unknown sourceType: %s", payload.sourceType)
        return error_response(
            f"Unknown source type '{payload.sourceType}'. Use 'upload' or 'text'.",
            status_code=400,
        )

    if not extracted_sources:
        return error_response(
            "No content could be extracted. Please provide valid files or text.",
            status_code=400,
        )

    successful = [s for s in extracted_sources if s["status"] == "success"]
    failed = [s for s in extracted_sources if s["status"] != "success"]
    total = len(extracted_sources)

    # ── Response status based on outcome ──────────────────────────────────────
    if len(successful) == 0:
        # All sources failed — return a proper error response
        logger.warning(
            "→ Response: 0/%d sources extracted — all failed", total,
        )
        first_error = failed[0]["error"] if failed else "No content could be extracted."
        return error_response(
            first_error if total == 1
            else f"All {total} file(s) failed to process. Please check your files and try again.",
            status_code=422,
        )

    if failed:
        # Partial success — log which files failed
        logger.warning(
            "→ Response: %d/%d sources extracted (%d failed: %s)",
            len(successful), total,
            len(failed),
            ", ".join(f["name"] for f in failed),
        )
    else:
        logger.info("→ Response: %d/%d sources extracted — all OK", len(successful), total)

    return success_response({
        "message": f"Extracted text from {len(successful)} of {total} source(s).",
        "extracted_sources": extracted_sources,
    })