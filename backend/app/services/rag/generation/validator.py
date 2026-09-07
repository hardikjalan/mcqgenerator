"""
validator.py
============
Refusing questions that should not reach a student.

A language model asked for structured output returns *well-formed* structured
output. It does not return *correct* output, and the failures are quiet: four
options where two say the same thing, a correct index pointing at the wrong
one, a question that reads well and is answerable only from knowledge the
passages never contained.

None of that is visible in the JSON. Each check below exists because the
alternative is a student sitting an exam with a broken question in it, and a
teacher who has no way to know which one.

Questions are dropped, never repaired. A question that fails these checks is
usually wrong in ways that patching the shape would hide.
"""

from __future__ import annotations

import re

from app.services.rag.generation.base import MCQ

# Below this, an "option" is a fragment rather than an answer.
_MIN_OPTION_CHARS = 1

# A correct answer several times longer than every distractor is the single
# most reliable giveaway in a badly written multiple-choice question — students
# learn to pick the long one without reading the stem.
_MAX_LENGTH_RATIO = 3.0

_BANNED_OPTIONS = ("all of the above", "none of the above", "both a and b")


def validate(questions: list[MCQ], *, passages: list[str]) -> tuple[list[MCQ], list[str]]:
    """Return (questions worth keeping, reasons the others were dropped)."""
    kept: list[MCQ] = []
    rejected: list[str] = []
    seen: set[str] = set()

    for question in questions:
        problem = _problem_with(question, passages, seen)
        if problem:
            rejected.append(f"{question.question[:60]}… — {problem}")
            continue

        seen.add(_fingerprint(question.question))
        kept.append(question)

    return kept, rejected


# ── Checks ────────────────────────────────────────────────────────────────────

def _problem_with(question: MCQ, passages: list[str], seen: set[str]) -> str | None:
    if not question.question.strip():
        return "empty question"

    options = [option.strip() for option in question.options]

    if len(options) != 4:
        return f"{len(options)} options, expected 4"

    if any(len(option) < _MIN_OPTION_CHARS for option in options):
        return "an empty option"

    # Case-insensitive: "Chlorophyll" and "chlorophyll" are one option twice,
    # which quietly turns a four-option question into a three-option one.
    lowered = [option.lower() for option in options]
    if len(set(lowered)) != 4:
        return "duplicate options"

    if not 0 <= question.correct_index < 4:
        return f"correct_index {question.correct_index} is out of range"

    if any(banned in option for option in lowered for banned in _BANNED_OPTIONS):
        return "uses an 'all/none of the above' option"

    lengths = [len(option) for option in options]
    correct_length = lengths[question.correct_index]
    others = [length for i, length in enumerate(lengths) if i != question.correct_index]
    if others and correct_length > _MAX_LENGTH_RATIO * max(others):
        return "the correct answer is conspicuously longer than the distractors"

    if _fingerprint(question.question) in seen:
        return "duplicate of an earlier question"

    if passages and not _is_grounded(question, passages):
        return "not supported by the source passages"

    return None


def _is_grounded(question: MCQ, passages: list[str]) -> bool:
    """Check the quoted evidence actually appears in the passages.

    The model is asked to quote the sentence its answer rests on, which is
    hard to do from memory and easy to do from the text — so a quote that
    cannot be found is the clearest signal available that the question was
    written from the model's own knowledge instead of the material.

    Matching is loose on purpose: whitespace and punctuation get normalised in
    transit, and rejecting a good question over a curly quote would be worse
    than the leniency costs.
    """
    evidence = " ".join(question.citations).strip()
    if not evidence:
        return False

    haystack = _normalise(" ".join(passages))

    for quote in question.citations:
        needle = _normalise(quote)
        if len(needle) < 20:
            continue
        if needle in haystack:
            return True

        # Long quotes drift — a model may join two sentences or trim a clause.
        # Falling back to a distinctive opening fragment keeps those.
        if len(needle) > 60 and needle[:60] in haystack:
            return True

    return False


def _normalise(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", "", text.lower()).replace("  ", " ").strip()


def _fingerprint(question: str) -> str:
    """Two questions differing only in wording should count as one."""
    return _normalise(question)[:120]
