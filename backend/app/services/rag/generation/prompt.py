"""
prompt.py
=========
Building the instruction sent to the model.

Two failure modes drive almost every line here.

**Writing from memory.** A model that knows biology will happily write a
correct, well-formed question about photosynthesis that appears nowhere in the
uploaded material. The teacher then sets an exam on content they did not
teach. So the passages are framed as the only permitted source, and the model
is asked to quote the sentence each answer rests on — a requirement that is
hard to satisfy from memory and easy to satisfy from the text.

**Giveaway distractors.** Left alone, models write one long specific correct
answer and three short vague wrong ones, which a student can pass without
reading the question. The instructions ask for plausible, similar-length
options drawn from the same material.
"""

from __future__ import annotations

from app.services.rag.generation.base import QuizBrief

SYSTEM_INSTRUCTION = (
    "You write multiple-choice exam questions for university and school "
    "teachers. You work strictly from the source passages you are given. You "
    "never use outside knowledge, even when you are confident it is correct, "
    "because the teacher is examining what they taught rather than what is "
    "true in general."
)


def build_prompt(brief: QuizBrief, passages: list[str], count: int) -> str:
    """Assemble the generation prompt."""
    numbered = "\n\n".join(
        f"[Passage {index + 1}]\n{passage}" for index, passage in enumerate(passages)
    )

    return f"""Write {count} multiple-choice questions from the source passages below.

COURSE CONTEXT
Subject: {brief.subject}
Topics to cover: {brief.topics}
Learning objective: {brief.objective}
Audience: {brief.grade_level}

SOURCE PASSAGES
{numbered}

RULES
1. Every question and every correct answer must be supported by the passages
   above. If the passages do not cover something, do not ask about it — write
   fewer questions instead. Do not use outside knowledge.
2. For each question, quote the exact sentence from the passages that makes
   the correct answer correct, in the "evidence" field. If you cannot quote
   one, drop the question.
3. Exactly four options. One is correct. The other three must be plausible to
   someone who has not studied the material properly — drawn from the same
   passages where possible, similar in length and specificity to the correct
   answer. Do not pad with obviously wrong options.
4. Do not signal the answer through length, detail or grammar. A student who
   has not read the passages should not be able to pick it out.
5. Avoid "all of the above", "none of the above", and double negatives.
6. Pitch the difficulty at the stated audience.
7. Each question must test something different. Do not rephrase one fact into
   several questions.
8. Write the explanation for the teacher: say why the answer is right and,
   briefly, why the closest wrong option is wrong.
9. Reference passages by their number in "passage_numbers".

Return fewer questions rather than inventing content the passages do not
support."""
