"""
routes.py
=========
The API endpoints.

Routes validate the request and shape the response. The work lives in
``app/services/`` — a route that grows a try/except around processing logic
has taken on work that belongs elsewhere.

Errors are raised as HTTPException. The handler in main.py turns every one of
them into ``{"error": "..."}``, so whatever is passed as the detail is shown to
the user verbatim. Keep it a plain sentence, never an internal message.

Note that ``generate_assessment`` is a plain ``def``, not ``async def``.
Downloading and parsing a document blocks; FastAPI runs sync endpoints in a
threadpool, so blocking here is correct, whereas blocking inside an ``async
def`` would stall the event loop for every other request.
"""

from fastapi import APIRouter, Depends, HTTPException

from app import config
from app.auth import AuthenticatedUser, current_user, owner_id
from app.schemas import (
    GenerateRequest,
    GenerateResponse,
    LimitsResponse,
    QuestionResponse,
    SearchHitResponse,
    SearchRequest,
    SearchResponse,
    SourceResult,
)
from app.services.extraction import ExtractedSource, SourceInput, extract_sources
from app.services.quiz import generate_quiz
from app.services.rag.generation import QuizBrief
from app.services.rag.generation.base import (
    GenerationUnavailableError,
    NoMaterialError,
)
from app.services.rag.ingestion.exceptions import IngestionError
from app.services.rag.retrieval import Retriever

router = APIRouter()


@router.get("/")
def health() -> dict[str, str]:
    """Liveness check."""
    return {"status": "ok"}


@router.get("/limits", response_model=LimitsResponse)
def limits() -> LimitsResponse:
    """The upload rules, so the frontend does not have to hardcode them.

    These caps were previously written down in three places with a comment in
    each asking the next person to keep the others in sync. Serving them is
    the only version of that which actually holds.
    """
    return LimitsResponse(
        maxFileBytes=config.MAX_FILE_BYTES,
        maxCumulativeBytes=config.MAX_CUMULATIVE_BYTES,
        allowedExtensions=list(config.ALLOWED_EXTENSIONS),
        ocrEnabled=config.ocr_enabled(),
    )


@router.post("/generate-assessment", response_model=GenerateResponse)
def generate_assessment(
    payload: GenerateRequest,
    user: AuthenticatedUser | None = Depends(current_user),
) -> GenerateResponse:
    """Read the uploaded material and write a quiz from it.

    Everything happens in one request: download, extract, chunk, index, then
    retrieve and generate. That makes it a slow request — tens of seconds for
    a large upload with OCR — which is the first thing to move to a background
    job if uploads get bigger. It is not split today because a two-call flow
    needs somewhere to keep the state between the calls, and that somewhere is
    the vector store, which is optional.
    """
    if payload.sourceType == "text":
        text = (payload.textContent or "").strip()
        if not text:
            raise HTTPException(400, "No text was provided.")
        return GenerateResponse(
            sources=[SourceResult(name="Pasted text", ok=True, chars=len(text))]
        )

    if not payload.files:
        raise HTTPException(400, "No files were provided.")

    extracted = extract_sources(
        [
            SourceInput(name=f.name, signed_url=f.signedUrl, size_bytes=f.size_bytes)
            for f in payload.files
        ],
        owner_id=owner_id(user),
    )

    questions, note = _write_quiz(payload, extracted, user)

    # A per-file failure is a row in the response, not an HTTP error — the
    # other files in the batch may have succeeded. Only a batch where nothing
    # could be read at all is worth failing the request over, and even then
    # the rows are more useful than a status code, so it stays a 200.
    return GenerateResponse(
        questions=questions,
        note=note,
        sources=[
            SourceResult(
                name=e.name,
                ok=e.ok,
                chars=e.chars,
                chunks=len(e.chunks or []),
                sourceId=e.source_id,
                indexed=e.indexed,
                indexNote=e.index_note,
                error=e.error,
            )
            for e in extracted
        ],
    )


def _write_quiz(
    payload: GenerateRequest,
    extracted: list[ExtractedSource],
    user: AuthenticatedUser | None,
) -> tuple[list[QuestionResponse], str | None]:
    """Generate questions from whatever was read successfully.

    Returns a note instead of raising when questions cannot be written. The
    files were still read, chunked and indexed by this point; turning that
    into an error would tell the teacher their upload failed when it did not.
    """
    usable = [source for source in extracted if source.ok]
    if not usable:
        return [], None

    brief = QuizBrief(
        subject=payload.config.subjectName,
        topics=payload.config.topicsCovered,
        objective=payload.config.learningObjective,
        grade_level=payload.config.gradeLevel,
        count=payload.config.questionCount,
    )

    fallback = [chunk for source in usable for chunk in (source.chunks or [])]

    try:
        result = generate_quiz(
            brief,
            source_ids=[s.source_id for s in usable if s.source_id and s.indexed],
            owner_id=owner_id(user),
            fallback_chunks=fallback,
        )
    except GenerationUnavailableError:
        return [], "Question generation isn't switched on, so your files were read but no quiz was written."
    except (NoMaterialError, IngestionError) as exc:
        if exc.detail:
            print(f"[quiz] {exc.detail}")
        return [], exc.message

    return [
        QuestionResponse(
            question=question.question,
            options=question.options,
            correctIndex=question.correct_index,
            explanation=question.explanation,
            evidence=question.citations,
        )
        for question in result.questions
    ], result.note


@router.post("/search", response_model=SearchResponse)
def search(
    payload: SearchRequest,
    user: AuthenticatedUser | None = Depends(current_user),
) -> SearchResponse:
    """Find the passages most likely to answer a question.

    Generation will call this internally rather than over HTTP; the endpoint
    exists so retrieval quality can be inspected directly, which is the only
    practical way to tune chunk size and the score floor.

    Two scopes apply. ``sourceIds`` comes from the client and narrows the
    search to the files this quiz is about — useful, but a claim. The owner
    comes from the verified token and is what actually keeps one faculty
    member out of another's material, enforced inside ``match_chunks`` rather
    than here.
    """
    question = payload.question.strip()
    if not question:
        raise HTTPException(400, "No question was provided.")
    if not payload.sourceIds:
        raise HTTPException(400, "No documents were selected to search.")

    retriever = Retriever()
    if not retriever.available:
        raise HTTPException(503, "Search isn't set up for this deployment yet.")

    try:
        hits = retriever.search(
            question,
            source_ids=payload.sourceIds,
            owner_id=owner_id(user),
            top_k=payload.topK,
        )
    except IngestionError as exc:
        if exc.detail:
            print(f"[search] {exc.detail}")
        raise HTTPException(502, exc.message) from exc

    return SearchResponse(
        hits=[
            SearchHitResponse(
                content=hit.content,
                score=round(hit.score, 4),
                fileName=hit.file_name,
                citation=hit.citation(),
                pageStart=hit.page_start,
                pageEnd=hit.page_end,
            )
            for hit in hits
        ]
    )
