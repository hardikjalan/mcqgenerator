"""Deterministic quality checks and evidence provenance verification."""
import re
import unicodedata
from difflib import SequenceMatcher
from statistics import median
from app.services.rag.generation.models import GeneratedQuestion


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip().casefold()


def validate_question(question: GeneratedQuestion, contexts: list, previous: list[GeneratedQuestion] | None = None) -> list[str]:
    errors = []
    options = [normalise(option) for option in question.options]
    answers = question.correct_answer if isinstance(question.correct_answer, list) else [question.correct_answer]
    if not question.question.strip() or len(question.question) > 3000:
        errors.append("Question text is empty or too long.")
    expected = 2 if question.question_type == "truefalse" else 4
    if len(options) != expected or any(not option for option in options) or len(set(options)) != len(options):
        errors.append("Options must be distinct, non-empty and match the question format.")
    if question.question_type == "truefalse" and set(options) != {"true", "false"}:
        errors.append("True/false options must be True and False.")
    if not answers or len({normalise(a) for a in answers}) != len(answers) or any(normalise(a) not in options for a in answers):
        errors.append("Every correct answer must exactly match a distinct option.")
    else:
        canonical = {normalise(option): option for option in question.options}
        question.correct_answer = [canonical[normalise(a)] for a in answers] if isinstance(question.correct_answer, list) else canonical[normalise(answers[0])]
    if question.question_type == "multiple":
        if not 2 <= len(answers) < len(options):
            errors.append("Multi-select needs at least two correct choices and one distractor.")
    elif len(answers) != 1 or isinstance(question.correct_answer, list):
        errors.append("Single and true/false questions need one answer string.")
    if not question.explanation.strip() or not question.topic.strip() or not question.bloom_rationale.strip():
        errors.append("Explanation, topic and cognitive rationale are required.")
    if len(options) == 4:
        lengths = [len(o.split()) for o in options]
        for answer in answers:
            if len(answer.split()) > max(18, median(lengths) * 3):
                errors.append("Correct answer length gives away the answer.")
    if any(SequenceMatcher(None, normalise(question.question), normalise(q.question)).ratio() > 0.9 for q in (previous or [])):
        errors.append("Question duplicates another question.")
    by_parent = {ctx.parent_id: ctx for ctx in contexts}
    if not question.evidence:
        errors.append("Quoted supporting evidence is required.")
    for evidence in question.evidence:
        ctx = by_parent.get(evidence.parent_id)
        if not ctx or ctx.source_id != evidence.source_id or normalise(evidence.quote) not in normalise(ctx.content):
            errors.append("Supporting quotation was not found in the specified source passage.")
        else:
            # Citations are copied from trusted extraction metadata, never model inventions.
            evidence.file_name = ctx.file_name
            evidence.page = ctx.page_or_slide_num
            evidence.pages = ctx.metadata.get("page_numbers") or ([ctx.page_or_slide_num] if ctx.page_or_slide_num else [])
    return errors
