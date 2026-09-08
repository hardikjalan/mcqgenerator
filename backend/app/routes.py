"""
routes.py
=========
The API endpoints.

Routes validate the request and shape the response. When extraction and
generation arrive they go in their own modules and get called from here — a
route that grows a try/except around processing logic has taken on work that
belongs elsewhere.

Errors are raised as HTTPException. The handler in main.py turns every one of
them into ``{"error": "..."}``, so whatever is passed as the detail is shown to
the user verbatim. Keep it a plain sentence, never an internal message.
"""

import logging
from fastapi import APIRouter, HTTPException

from app.schemas import GenerateRequest, GenerateResponse, SourceResult
from app.services.rag.pipeline import run_assessment_pipeline

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@router.post("/generate-assessment", response_model=GenerateResponse)
def generate_assessment(payload: GenerateRequest) -> GenerateResponse:
    """Execute the end-to-end RAG pipeline for teacher assessment generation."""
    if payload.sourceType == "text":
        text = (payload.textContent or "").strip()
        if not text:
            raise HTTPException(400, "No text was provided.")
        return GenerateResponse(
            sources=[SourceResult(name="Pasted text", ok=True, chars=len(text))]
        )

    if not payload.files:
        raise HTTPException(400, "No files were provided.")

    try:
        sources, retrieval_result, questions = run_assessment_pipeline(payload)
        return GenerateResponse(sources=sources, questions=questions)
    except RuntimeError as exc:
        logger.error("Pipeline service error: %s", exc)
        raise HTTPException(503, str(exc))
    except ValueError as exc:
        logger.error("Pipeline validation error: %s", exc)
        raise HTTPException(422, str(exc))
    except Exception as exc:
        logger.error("Unhandled error in assessment pipeline: %s", exc)
        raise HTTPException(500, f"Assessment pipeline failed: {exc}")

