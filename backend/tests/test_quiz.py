"""
test_quiz.py
============
The RAG loop: choosing passages, then writing questions from them.

Both the retriever and the generator are faked. What is under test is the
orchestration — that every topic gets searched, that batches see different
material, and that "nothing relevant was found" is treated as an answer rather
than as a reason to improvise.
"""

from __future__ import annotations

import pytest

from app.services.quiz import generate_quiz
from app.services.rag.generation import MCQ, QuizBrief
from app.services.rag.generation.base import GenerationUnavailableError, NoMaterialError
from app.services.rag.store.base import SearchHit

BRIEF = QuizBrief(
    subject="Biology",
    topics="photosynthesis, genetics, cell division",
    objective="Understand energy capture in plants",
    grade_level="Undergraduate",
    count=4,
)


class FakeRetriever:
    def __init__(self, hits_per_query: int = 3, available: bool = True) -> None:
        self.available = available
        self.queries: list[str] = []
        self.owner_ids: list[str | None] = []
        self._n = hits_per_query

    def search(self, question, *, source_ids=None, owner_id=None, top_k=None, min_score=None):
        self.queries.append(question)
        self.owner_ids.append(owner_id)
        return [
            SearchHit(
                id=f"{abs(hash(question))}-{i}", source_id="s1", file_name="lecture.pdf",
                content=f"passage for {question} number {i}", score=0.9,
                page_start=i + 1, page_end=i + 1,
            )
            for i in range(self._n)
        ]


class FakeGenerator:
    """Returns one valid, grounded question per request."""

    name = "fake"

    def __init__(self, per_call: int | None = None) -> None:
        self.calls: list[list[str]] = []
        self._per_call = per_call

    def generate(self, brief, passages, count):
        self.calls.append(list(passages))
        made = count if self._per_call is None else self._per_call
        return [
            MCQ(
                question=f"Question {len(self.calls)}.{i} about {brief.subject}?",
                options=["alpha one", "beta two", "gamma three", "delta four"],
                correct_index=0,
                citations=[passages[0][:80]] if passages else [],
            )
            for i in range(made)
        ]


class FakeChunk:
    def __init__(self, text: str) -> None:
        self.text = text


# ── Passage selection ─────────────────────────────────────────────────────────

def test_every_topic_is_searched_separately():
    """One search for 'photosynthesis, genetics, cell division' returns
    whatever sits closest to that blurred average — usually all of one topic."""
    retriever = FakeRetriever()

    generate_quiz(BRIEF, source_ids=["s1"], retriever=retriever, generator=FakeGenerator())

    assert any("photosynthesis" in q for q in retriever.queries)
    assert any("genetics" in q for q in retriever.queries)
    assert any("cell division" in q for q in retriever.queries)


def test_the_objective_is_searched_too():
    retriever = FakeRetriever()

    generate_quiz(BRIEF, source_ids=["s1"], retriever=retriever, generator=FakeGenerator())

    assert BRIEF.objective in retriever.queries


def test_the_owner_is_passed_to_every_search():
    """The fence that keeps one teacher out of another's material."""
    retriever = FakeRetriever()

    generate_quiz(
        BRIEF, source_ids=["s1"], owner_id="teacher-a",
        retriever=retriever, generator=FakeGenerator(),
    )

    assert set(retriever.owner_ids) == {"teacher-a"}


def test_results_are_interleaved_across_topics():
    """A truncated passage list should still span the syllabus, so the best
    hit from each topic comes before the second hit from any of them."""
    generator = FakeGenerator()

    generate_quiz(BRIEF, source_ids=["s1"], retriever=FakeRetriever(), generator=generator)

    first_window = generator.calls[0]
    topics_in_first_three = {p.split("number")[0] for p in first_window[:3]}
    assert len(topics_in_first_three) == 3


def test_duplicate_chunks_are_not_repeated():
    """The same chunk can be the best answer for two topics."""

    class OneHit(FakeRetriever):
        def search(self, question, **kwargs):
            self.queries.append(question)
            return [SearchHit(id="same", source_id="s1", file_name="f.pdf",
                              content="shared passage", score=0.9)]

    generator = FakeGenerator()
    generate_quiz(BRIEF, source_ids=["s1"], retriever=OneHit(), generator=generator)

    assert len(generator.calls[0]) == 1


# ── Nothing relevant ──────────────────────────────────────────────────────────

def test_no_relevant_material_is_an_answer_not_a_guess():
    """The score floor rejecting everything means the uploads do not cover
    these topics. Falling back to raw chunks here would paper over exactly the
    case the floor exists to catch."""

    class NoHits(FakeRetriever):
        def search(self, question, **kwargs):
            return []

    with pytest.raises(NoMaterialError) as excinfo:
        generate_quiz(BRIEF, source_ids=["s1"], retriever=NoHits(), generator=FakeGenerator())

    assert BRIEF.topics in excinfo.value.message


def test_without_a_generator_it_says_so():
    with pytest.raises(GenerationUnavailableError):
        generate_quiz(BRIEF, source_ids=["s1"], retriever=FakeRetriever(), generator=None)


# ── Working without a vector store ────────────────────────────────────────────

def test_chunks_are_used_when_there_is_no_search():
    """A deployment with a Gemini key but no Supabase should still produce a
    quiz — the uploads are capped at 5MB, so using them whole is reasonable."""
    generator = FakeGenerator()

    result = generate_quiz(
        BRIEF,
        source_ids=[],
        fallback_chunks=[
            FakeChunk(
                f"Passage {i}: chlorophyll absorbs photons in the thylakoid "
                f"membrane and the Calvin cycle fixes carbon dioxide."
            )
            for i in range(10)
        ],
        retriever=FakeRetriever(available=False),
        generator=generator,
    )

    assert result.questions
    assert "Search isn't set up" in result.note


def test_nothing_at_all_is_refused():
    with pytest.raises(NoMaterialError):
        generate_quiz(
            BRIEF, source_ids=[], fallback_chunks=[],
            retriever=FakeRetriever(available=False), generator=FakeGenerator(),
        )


# ── Generating ────────────────────────────────────────────────────────────────

def test_batches_see_different_passages():
    """Handing the same passages to every batch produces the same questions in
    different words."""
    generator = FakeGenerator(per_call=1)
    brief = QuizBrief(**{**BRIEF.__dict__, "count": 3})

    generate_quiz(brief, source_ids=["s1"], retriever=FakeRetriever(hits_per_query=8),
                  generator=generator)

    assert len(generator.calls) >= 2
    assert generator.calls[0] != generator.calls[1]


def test_the_requested_count_is_respected():
    generator = FakeGenerator(per_call=10)

    result = generate_quiz(BRIEF, source_ids=["s1"], retriever=FakeRetriever(),
                           generator=generator)

    assert len(result.questions) == BRIEF.count


def test_the_ceiling_overrides_an_absurd_request():
    from app import config

    brief = QuizBrief(**{**BRIEF.__dict__, "count": 5000})
    result = generate_quiz(brief, source_ids=["s1"], retriever=FakeRetriever(),
                           generator=FakeGenerator(per_call=50))

    assert len(result.questions) <= config.MAX_QUESTIONS


def test_a_generator_producing_nothing_stops_rather_than_looping():
    """The passages and the prompt do not change between attempts, so a batch
    that produced nothing will keep producing nothing."""

    class Empty(FakeGenerator):
        def generate(self, brief, passages, count):
            self.calls.append(list(passages))
            return []

    generator = Empty()

    result = generate_quiz(BRIEF, source_ids=["s1"], retriever=FakeRetriever(),
                           generator=generator)

    assert result.questions == []
    assert len(generator.calls) == 1


def test_a_shortfall_is_explained():
    """A teacher who asked for four and got two needs to know why."""
    generator = FakeGenerator(per_call=1)

    class OnceThenNothing(FakeGenerator):
        def generate(self, brief, passages, count):
            self.calls.append(list(passages))
            if len(self.calls) > 2:
                return []
            return FakeGenerator.generate(self, brief, passages, 1)

    result = generate_quiz(BRIEF, source_ids=["s1"], retriever=FakeRetriever(),
                           generator=OnceThenNothing())

    assert 0 < len(result.questions) < BRIEF.count
    assert "did not support more" in result.note
