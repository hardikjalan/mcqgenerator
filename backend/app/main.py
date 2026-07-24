"""
main.py
=======
FastAPI application entry point for the MCQ Generator backend.

Run from the backend/ directory:
    uvicorn app.main:app --reload

This module owns app setup only — middleware, global exception handlers, and
router mounting. Endpoint logic lives in app/api/routes/, request shapes in
app/schemas/, and processing in app/services/.

All pipeline errors (validation, loading, extraction) are converted to
frontend-safe JSON responses here. Internal details are logged but never
exposed to the client.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import assessments, health
from app.core.config import ALLOWED_ORIGINS
from app.core.exceptions import DocumentProcessingError
from app.core.logger import get_logger
from app.core.responses import error_response

logger = get_logger(__name__)

# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(
    title="MCQ Generator API",
    description="Backend API for extracting text from documents and generating assessments.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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

# ── Routes ────────────────────────────────────────────────────────────────────

app.include_router(health.router)
app.include_router(assessments.router)
