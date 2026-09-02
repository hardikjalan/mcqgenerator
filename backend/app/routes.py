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

from fastapi import APIRouter, HTTPException

from app.schemas import GenerateRequest, GenerateResponse, SourceResult

router = APIRouter()


@router.get("/")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@router.post("/generate-assessment", response_model=GenerateResponse)
def generate_assessment(payload: GenerateRequest) -> GenerateResponse:
    """Turn uploaded files or pasted text into per-source extraction results."""
    if payload.sourceType == "text":
        text = (payload.textContent or "").strip()
        if not text:
            raise HTTPException(400, "No text was provided.")
        return GenerateResponse(
            sources=[SourceResult(name="Pasted text", ok=True, chars=len(text))]
        )

    if not payload.files:
        raise HTTPException(400, "No files were provided.")

    # Not built yet. Returning empty or zeroed results here would look like a
    # successful extraction that found nothing, which is the confusing failure
    # this is meant to avoid — so say so plainly instead.
    raise HTTPException(
        501,
        "File extraction is not available yet. Paste your text in the meantime.",
    )
