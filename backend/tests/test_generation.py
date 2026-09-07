"""
test_generation.py
==================
Layer 4 — writing questions, and refusing the ones that should not reach a
student.

The validator gets most of the attention here. Structured output guarantees
the *shape* of what the model returns; nothing guarantees the sense of it, and
every check below exists because the alternative is a broken question in a
real exam that nobody can spot from the JSON.
"""

from __future__ import annotations

import pytest

from app.services.rag.generation import MCQ, QuizBrief, validate
from app.services.rag.generation.gemini import _parse

PASSAGE = (
    "Chlorophyll absorbs photons in the thylakoid membrane, exciting electrons "
    "that pass along an electron transport chain. The Calvin cycle fixes carbon "
    "dioxide onto ribulose bisphosphate using the enzyme RuBisCO."
)


def _mcq(**overrides) -> MCQ:
    defaults = dict(
        question="Where does chlorophyll absorb photons?",
        options=["The thylakoid membrane", "The stroma", "The cell wall", "The nucleus"],
        correct_index=0,
        explanation="Stated directly in the passage.",
        citations=["Chlorophyll absorbs photons in the thylakoid membrane"],
    )
    defaults.update(overrides)
    return MCQ(**defaults)


def _keep(question: MCQ) -> bool:
    kept, _ = validate([question], passages=[PASSAGE])
    return len(kept) == 1


# ── A good question survives ──────────────────────────────────────────────────

def test_a_well_formed_grounded_question_is_kept():
    assert _keep(_mcq()) is True


def test_the_reason_for_a_rejection_is_reported():
    """Silently dropping questions leaves a teacher wondering why they asked
    for ten and got six."""
    _, rejected = validate([_mcq(correct_index=9)], passages=[PASSAGE])

    assert len(rejected) == 1
    assert "out of range" in rejected[0]


# ── Shape ─────────────────────────────────────────────────────────────────────

def test_three_options_is_not_a_multiple_choice_question():
    assert _keep(_mcq(options=["a", "b", "c"])) is False


def test_an_out_of_range_answer_is_refused():
    """The index points at nothing — the question has no correct answer at
    all, and no reader of the JSON would notice."""
    assert _keep(_mcq(correct_index=4)) is False


def test_duplicate_options_are_refused():
    """Two identical options quietly turn a four-option question into a
    three-option one, changing the odds of guessing."""
    assert _keep(_mcq(options=[
        "The thylakoid membrane", "the thylakoid membrane", "The stroma", "The nucleus",
    ])) is False


def test_an_empty_option_is_refused():
    assert _keep(_mcq(options=["The thylakoid membrane", "", "The stroma", "The nucleus"])) is False


# ── Quality ───────────────────────────────────────────────────────────────────

def test_all_of_the_above_is_refused():
    assert _keep(_mcq(options=[
        "The thylakoid membrane", "The stroma", "The nucleus", "All of the above",
    ])) is False


def test_a_conspicuously_long_correct_answer_is_refused():
    """The most reliable giveaway in a badly written question — students learn
    to pick the long one without reading the stem."""
    assert _keep(_mcq(options=[
        "The thylakoid membrane, which is the internal membrane system of the "
        "chloroplast where the light-dependent reactions of photosynthesis occur",
        "The stroma",
        "The wall",
        "The nucleus",
    ])) is False


def test_a_repeated_question_is_dropped():
    """Ten questions that are one fact reworded ten times is not a quiz."""
    kept, rejected = validate([_mcq(), _mcq()], passages=[PASSAGE])

    assert len(kept) == 1
    assert "duplicate" in rejected[0]


# ── Grounding ─────────────────────────────────────────────────────────────────

def test_a_question_the_passages_do_not_support_is_refused():
    """The failure this whole layer exists to prevent: a correct, well-written
    question about something the teacher never taught."""
    invented = _mcq(
        question="Who first described the citric acid cycle?",
        options=["Hans Krebs", "Melvin Calvin", "Peter Mitchell", "Rosalind Franklin"],
        citations=["Hans Krebs described the citric acid cycle in 1937"],
    )

    assert _keep(invented) is False


def test_a_question_with_no_evidence_at_all_is_refused():
    assert _keep(_mcq(citations=[])) is False


def test_punctuation_differences_do_not_reject_a_good_question():
    """Quotes drift in transit — curly apostrophes, lost commas. Rejecting a
    sound question over a character would cost more than the leniency does."""
    assert _keep(_mcq(citations=["Chlorophyll absorbs photons, in the thylakoid membrane!"])) is True


def test_grounding_is_skipped_when_there_are_no_passages():
    """Nothing to check against is not the same as failing the check."""
    kept, _ = validate([_mcq(citations=[])], passages=[])
    assert len(kept) == 1


# ── Parsing the model's reply ─────────────────────────────────────────────────

def test_a_valid_reply_becomes_questions():
    raw = """[{"question": "Q?", "options": ["a", "b", "c", "d"],
               "correct_index": 2, "explanation": "why",
               "evidence": ["quote"], "passage_numbers": [1]}]"""

    (question,) = _parse(raw, [PASSAGE])

    assert question.correct_index == 2
    assert question.citations == ["quote"]
    assert question.source_chunk_ids == ["1"]


def test_an_unparseable_reply_loses_only_that_batch():
    """Other batches may be fine; three good questions beats an error because
    the fourth request misbehaved."""
    assert _parse("I'd be happy to help! Here are your questions:", [PASSAGE]) == []


def test_a_malformed_question_is_skipped_not_fatal():
    raw = """[{"question": "Good?", "options": ["a","b","c","d"], "correct_index": 0, "evidence": []},
              {"question": "Bad — no options"}]"""

    questions = _parse(raw, [PASSAGE])

    assert len(questions) == 1
    assert questions[0].question == "Good?"


def test_a_passage_number_out_of_range_is_dropped():
    raw = """[{"question": "Q?", "options": ["a","b","c","d"], "correct_index": 0,
               "evidence": [], "passage_numbers": [1, 99]}]"""

    (question,) = _parse(raw, [PASSAGE])

    assert question.source_chunk_ids == ["1"]
