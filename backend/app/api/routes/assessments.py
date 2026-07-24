"""
assessments.py
==============
Faculty-side assessment routes — turning uploaded material into questions.

Routes here stay thin: validate the request, delegate to a service, shape the
response. Extraction logic lives in app/services/extraction/pipeline.py.
"""

from fastapi import APIRouter

from app.core.config import MAX_CUMULATIVE_SIZE_MB
from app.core.logger import get_logger
from app.core.responses import success_response, error_response
from app.schemas.assessment import GenerateRequest
from app.services.extraction.pipeline import download_and_extract

logger = get_logger(__name__)

router = APIRouter(tags=["assessments"])


@router.post("/generate-assessment")
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
