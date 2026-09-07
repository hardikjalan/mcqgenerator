"""
quiz.py
=======
Turning extracted material into a quiz.

The RAG loop lives here: pick the passages, hand them to the model, check what
comes back. The layers below know nothing about quizzes and this module knows
nothing about HTTP.

Two decisions shape it.

**Passages are chosen per topic, not per quiz.** A single search for
"photosynthesis, respiration, genetics" returns whatever sits closest to that
blurred average — often eight chunks about one of the three. Searching each
topic separately and interleaving the results is what makes a quiz that covers
the syllabus rather than its first item.

**Each batch of questions sees different passages.** Handing the same six
chunks to every batch produces the same questions in different words. Rotating
the window is the cheapest way to get breadth out of a model that has no
memory of the previous call.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app import config
from app.services.rag.generation import (
    MCQ,
    NoMaterialError,
    QuizBrief,
    get_generator,
    validate,
)
from app.services.rag.generation.base import GenerationUnavailableError
from app.services.rag.retrieval import Retriever


@dataclass
class QuizResult:
    """Generated questions, plus what happened while making them."""

    questions: list[MCQ] = field(default_factory=list)
    passages_used: int = 0
    rejected: list[str] = field(default_factory=list)
    note: str | None = None


def generate_quiz(
    brief: QuizBrief,
    *,
    source_ids: list[str],
    owner_id: str | None = None,
    fallback_chunks: list[Any] | None = None,
    retriever: Retriever | None = None,
    generator: Any | None = None,
) -> QuizResult:
    """Write a quiz from the indexed material.

    Parameters
    ----------
    brief:
        What the faculty member configured.
    source_ids:
        The uploads this quiz may draw on.
    owner_id:
        The authenticated user, so retrieval cannot reach anyone else's rows.
    fallback_chunks:
        Chunks from the current request, used when there is no vector store to
        search. Keeps generation working on a deployment that has a Gemini key
        but no Supabase — the uploads are small enough that using them whole
        is reasonable.
    """
    generator = generator if generator is not None else get_generator()
    if generator is None:
        raise GenerationUnavailableError()

    retriever = retriever if retriever is not None else Retriever()

    passages, note = _gather_passages(
        brief, source_ids, owner_id, fallback_chunks, retriever
    )
    if not passages:
        raise NoMaterialError(brief.topics)

    count = max(1, min(brief.count, config.MAX_QUESTIONS))
    questions = _generate_in_batches(generator, brief, passages, count)

    kept, rejected = validate(questions, passages=passages)

    for reason in rejected:
        print(f"[quiz] rejected: {reason}")

    return QuizResult(
        questions=kept[:count],
        passages_used=len(passages),
        rejected=rejected,
        note=_shortfall_note(len(kept), count) or note,
    )


# ── Passage selection ─────────────────────────────────────────────────────────

def _gather_passages(
    brief: QuizBrief,
    source_ids: list[str],
    owner_id: str | None,
    fallback_chunks: list[Any] | None,
    retriever: Retriever,
) -> tuple[list[str], str | None]:
    """Collect the passages worth writing questions from."""
    if retriever.available and source_ids:
        passages = _retrieve(brief, source_ids, owner_id, retriever)
        if passages:
            return passages, None
        # Retrieval working and returning nothing is a real answer: the score
        # floor rejected everything, meaning the material does not cover these
        # topics. Falling back to raw chunks here would paper over exactly the
        # situation the floor exists to catch.
        return [], None

    if fallback_chunks:
        limit = config.GENERATION_CONTEXT_CHUNKS * 3
        return (
            [chunk.text for chunk in fallback_chunks[:limit]],
            "Search isn't set up, so questions were written from the start of "
            "the uploaded material rather than the parts most relevant to your "
            "topics.",
        )

    return [], None


def _retrieve(
    brief: QuizBrief,
    source_ids: list[str],
    owner_id: str | None,
    retriever: Retriever,
) -> list[str]:
    """Search once per topic and interleave, so every topic gets a look in."""
    seen: set[str] = set()
    per_topic: list[list[str]] = []

    for query in _queries(brief):
        hits = retriever.search(query, source_ids=source_ids, owner_id=owner_id)
        fresh = []
        for hit in hits:
            if hit.id in seen:
                continue
            seen.add(hit.id)
            fresh.append(f"{hit.content}\n(— {hit.citation()})")
        per_topic.append(fresh)

    # Round-robin rather than concatenate: taking the best of each topic first
    # means a truncated list still spans the syllabus.
    interleaved: list[str] = []
    for rank in range(max((len(group) for group in per_topic), default=0)):
        for group in per_topic:
            if rank < len(group):
                interleaved.append(group[rank])

    return interleaved


def _queries(brief: QuizBrief) -> list[str]:
    """One search per topic, plus the objective."""
    topics = [topic.strip() for topic in brief.topics.replace(";", ",").split(",")]
    queries = [f"{brief.subject} {topic}".strip() for topic in topics if topic]

    if brief.objective.strip():
        queries.append(brief.objective.strip())

    return queries or [brief.subject or brief.topics]


# ── Generation ────────────────────────────────────────────────────────────────

def _generate_in_batches(
    generator: Any,
    brief: QuizBrief,
    passages: list[str],
    count: int,
) -> list[MCQ]:
    """Ask for questions a few at a time, moving the passage window each time."""
    window = config.GENERATION_CONTEXT_CHUNKS
    batch_size = config.GENERATION_BATCH_SIZE

    questions: list[MCQ] = []
    batch_number = 0

    while len(questions) < count:
        wanted = min(batch_size, count - len(questions))
        start = (batch_number * window) % max(1, len(passages))
        window_passages = _window(passages, start, window)

        produced = generator.generate(brief, window_passages, wanted)
        questions.extend(produced)

        batch_number += 1

        # A batch that produces nothing will keep producing nothing — the
        # passages are the same kind of thing and so is the prompt. Stopping
        # returns what we have instead of spending the teacher's time proving
        # it again.
        if not produced:
            break

    return questions


def _window(passages: list[str], start: int, size: int) -> list[str]:
    """A wrapping slice, so the last batch still gets a full window."""
    if len(passages) <= size:
        return passages
    return [passages[(start + offset) % len(passages)] for offset in range(size)]


def _shortfall_note(produced: int, asked: int) -> str | None:
    if produced >= asked:
        return None
    if produced == 0:
        return None  # handled as an error upstream
    return (
        f"Wrote {produced} of the {asked} questions requested — the material "
        "did not support more without repeating itself."
    )
