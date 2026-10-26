"""Authenticated generation endpoint; detailed diagnostics stay in server logs."""
import logging
from fastapi import APIRouter, Depends, HTTPException
from app.auth import Actor, faculty
from app.schemas import GenerateRequest, GenerateResponse
from app.services.rag.pipeline import run_assessment_pipeline
from app.services.assessment import save_draft

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/")
def health():
    return {"status": "ok"}

@router.post("/generate-assessment", response_model=GenerateResponse)
def generate_assessment(payload: GenerateRequest, actor: Actor = Depends(faculty)):
    try:
        sources, retrieval, questions = run_assessment_pipeline(payload, actor.id)
        assessment = save_draft(actor, payload.config, questions)
        return GenerateResponse(sources=sources, questions=questions, assessmentId=assessment["id"])
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Assessment service unavailable")
        raise HTTPException(503, "The AI or indexing service is temporarily unavailable. Please retry shortly.") from exc
    except Exception as exc:
        logger.exception("Assessment generation failed")
        raise HTTPException(500, "Assessment generation failed. Please retry or contact support.") from exc

