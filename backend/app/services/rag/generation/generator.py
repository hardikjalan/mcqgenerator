"""
generator.py
============
Layer 6 Coordinator: MCQGenerator.
Uses Google Gemini to generate assessment questions grounded strictly
in Layer 5 retrieved parent contexts.
"""

from __future__ import annotations

import logging
import os
import time
from collections import Counter
from google import genai
from google.genai import errors, types

from app.schemas import QuizConfig
from app.services.adaptive import DIFFICULTIES, PoolPlan, plan_pool
from app.services.rag.retrieval.models import RetrievedParentContext
from app.services.rag.generation.models import (
    BLOOM_LEVELS,
    GeneratedQuestion,
    GeneratedQuiz,
    GenerationConfig,
)

logger = logging.getLogger(__name__)


# Tagging rubric sent with every generation request.
#
# The wording fights label inflation on purpose. Left to itself a model reaches
# for "analyze" because it sounds like a better question, so the rubric names the
# distinction it actually gets wrong - cognitive demand vs subject difficulty -
# and tells it to round DOWN when a question sits between two levels. An
# over-tagged quiz is worse than an untagged one: it tells a teacher their
# assessment probes deep thinking when it only asks for recall.
_BLOOM_TAGGING_RULES = """Tag every question with the Bloom's taxonomy level a student must operate at
to answer it. Judge the THINKING THE QUESTION DEMANDS, not how advanced the
subject matter is: a question on a difficult topic is still 'remember' if the
student only has to recall a fact stated in the material.

- remember:   Recall a fact, definition, term, date, or list stated in the material.
- understand: Explain an idea in other words, summarise, classify, compare, or
              recognise an example of a concept given in the material.
- apply:      Use a rule, formula, procedure, or principle to reach a result for a
              case that is NOT already worked out in the material.
- analyze:    Break something apart - separate cause from effect, identify an
              unstated assumption, infer a relationship, or explain why something
              fails.
- evaluate:   Judge against a criterion - decide which claim is best supported,
              which critique is strongest, or which approach is most defensible.

Be conservative and honest. Most questions written directly from reference text
are 'remember' or 'understand'. Do NOT label a question 'analyze' or 'evaluate'
because it seems more impressive. If a question sits between two levels, choose
the LOWER one."""


# Difficulty is deliberately judged on different evidence from Bloom's level.
#
# Left undefined, a model collapses the two into one axis and difficulty becomes
# a copy of bloom_level. They are genuinely independent: a 'remember' question
# can be hard (an obscure figure buried in a footnote) and an 'apply' question
# can be easy (substitute two numbers into a formula the text already gives).
# So this rubric asks about the ANSWER's retrievability and the distractors,
# never about the kind of thinking involved.
_DIFFICULTY_TAGGING_RULES = """Tag every question with how hard it is to ANSWER CORRECTLY. Judge it on three
things only - how directly the answer appears in the source, how many steps are
needed, and how tempting the wrong options are. Do NOT base difficulty on the
Bloom level; the two are independent.

- easy:   The answer is stated almost verbatim in the material and is easy to
          locate. One step. The wrong options are clearly wrong to anyone who
          read the passage.
- medium: The answer needs the right passage to be recalled and applied, or two
          facts to be combined. At least one wrong option is plausible enough to
          catch a student who skimmed.
- hard:   The answer requires several steps, an easily-missed detail, or a
          distinction between two things the material treats similarly. More
          than one wrong option is genuinely tempting, and a student who half
          understands will pick one.

Spread the difficulties honestly. Do not label a question 'hard' just because
the topic is advanced, and do not make a question hard by being vague or
ambiguous - a hard question is still precisely answerable from the material."""


class MCQGenerator:
    """Generates RAG-grounded multiple-choice questions via Google Gemini."""

    def __init__(
        self,
        config: GenerationConfig | None = None,
        client: genai.Client | None = None,
    ) -> None:
        self.config = config or GenerationConfig()
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if client is not None:
            self.client = client
        elif api_key:
            self.client = genai.Client(api_key=api_key)
        else:
            self.client = genai.Client()

    def generate_adaptive_pool(
        self,
        contexts: list[RetrievedParentContext],
        quiz_config: QuizConfig,
    ) -> tuple[list[GeneratedQuestion], PoolPlan]:
        """Generate a pool large enough for any path through the difficulty ladder.

        An adaptive quiz asks ``quiz_config.questionCount`` questions, but which
        ones depends on how the student answers, so the pool has to cover every
        path. ``plan_pool`` derives the per-bucket sizes from the ladder rules;
        see app/services/adaptive.py for why they are what they are.
        """
        plan = plan_pool(quiz_config.questionCount)
        logger.info(
            "Adaptive pool for a %d-question quiz: easy=%d, medium=%d, hard=%d (%d total)",
            plan.quiz_length, plan.easy, plan.medium, plan.hard, plan.total,
        )
        return self.generate_assessment(contexts, quiz_config, pool_plan=plan), plan

    def generate_assessment(
        self,
        contexts: list[RetrievedParentContext],
        quiz_config: QuizConfig,
        pool_plan: PoolPlan | None = None,
    ) -> list[GeneratedQuestion]:
        """Generate questions grounded strictly in the retrieved contexts.

        Parameters
        ----------
        contexts : list[RetrievedParentContext]
            Retrieved parent context chunks from Layer 5.
        quiz_config : QuizConfig
            Teacher configuration (subject, topics, objective, question count, type).

        Returns
        -------
        list[GeneratedQuestion]
            Exactly `quiz_config.questionCount` generated questions.

        Raises
        ------
        ValueError
            If retrieved contexts are empty or if the model fails to return the
            exact required question count after retry.
        """
        if not contexts:
            raise ValueError("Cannot generate questions: no retrieved context provided.")

        # With a pool plan the target is the pool total, not the quiz length:
        # the quiz asks questionCount questions, but the pool must hold enough
        # of each difficulty for every path the student could take.
        target_count = pool_plan.total if pool_plan else quiz_config.questionCount
        if target_count < 1:
            raise ValueError("Target question count must be at least 1.")

        if pool_plan:
            difficulty_mix_rules = (
                "=== REQUIRED DIFFICULTY MIX ===\n"
                f"Of the {target_count} questions, produce EXACTLY:\n"
                f"- {pool_plan.easy} with difficulty 'easy'\n"
                f"- {pool_plan.medium} with difficulty 'medium'\n"
                f"- {pool_plan.hard} with difficulty 'hard'\n"
                "These counts are a hard requirement, not a guideline. The quiz adapts to\n"
                "the student, so a shortfall in any one bucket breaks it.\n"
                "Each question must still be distinct: do not pad a bucket by restating a\n"
                "question you have already written at another difficulty.\n\n"
            )
        else:
            difficulty_mix_rules = ""

        # 1. Assemble context blocks
        context_blocks = []
        for i, ctx in enumerate(contexts, start=1):
            source_info = f"Source: {ctx.file_name}"
            if ctx.page_or_slide_num:
                source_info += f", Page/Slide: {ctx.page_or_slide_num}"
            if ctx.heading:
                source_info += f", Section: {ctx.heading}"
            context_blocks.append(f"--- Context Passage {i} [{source_info}] ---\n{ctx.content}")

        combined_context = "\n\n".join(context_blocks)

        # 2. Build instructions based on question type
        q_type = (quiz_config.questionType or "single").lower()
        if q_type == "single":
            type_rules = (
                "Format: SINGLE CHOICE questions only.\n"
                "- Every question must have EXACTLY 4 options.\n"
                "- Exactly 1 option must be correct.\n"
                "- `correct_answer` must be a single string matching the exact text of the correct option."
            )
        elif q_type == "multiple":
            type_rules = (
                "Format: MULTIPLE CHOICE (multi-select) questions only.\n"
                "- Every question must have EXACTLY 4 options.\n"
                "- At least 2 options must be correct.\n"
                "- `correct_answer` must be a list of strings matching the exact text of each correct option."
            )
        elif q_type == "truefalse":
            type_rules = (
                "Format: TRUE / FALSE questions only.\n"
                "- Every question must have EXACTLY 2 options: ['True', 'False'].\n"
                "- `correct_answer` must be a single string: either 'True' or 'False'."
            )
        else:  # 'all'
            type_rules = (
                "Format: MIXED format questions (balanced mixture of single choice, multiple choice, and true/false).\n"
                "- For single choice: exactly 4 options, 1 correct answer (string).\n"
                "- For multiple choice: exactly 4 options, 2+ correct answers (list of strings).\n"
                "- For true/false: exactly 2 options ['True', 'False'], 1 correct answer (string)."
            )

        prompt = (
            f"You are an expert assessment author. Generate an academic assessment based on the provided reference material.\n\n"
            f"=== TARGET PARAMETERS ===\n"
            f"Subject: {quiz_config.subjectName}\n"
            f"Target Audience / Grade Level: {quiz_config.gradeLevel}\n"
            f"Topics to Cover: {quiz_config.topicsCovered}\n"
            f"Learning Objective: {quiz_config.learningObjective}\n"
            f"Total Number of Questions: EXACTLY {target_count}\n\n"
            f"=== QUESTION FORMAT RULES ===\n"
            f"{type_rules}\n\n"
            f"=== COGNITIVE LEVEL TAGGING ===\n"
            f"{_BLOOM_TAGGING_RULES}\n\n"
            f"=== DIFFICULTY TAGGING ===\n"
            f"{_DIFFICULTY_TAGGING_RULES}\n\n"
            f"{difficulty_mix_rules}"
            f"=== STRICT GENERATION CONSTRAINTS ===\n"
            f"1. You MUST generate questions grounded ONLY in the reference context provided below.\n"
            f"2. Do NOT invent information, facts, or assumptions outside the reference context.\n"
            f"3. You MUST generate EXACTLY {target_count} questions. Returning fewer or more than {target_count} is invalid.\n"
            f"4. For each question, output ONLY:\n"
            f"   - `id`: sequential integer (1 to {target_count})\n"
            f"   - `question`: clear question text\n"
            f"   - `options`: array of choices\n"
            f"   - `correct_answer`: correct choice text or array of choices\n"
            f"   - `question_type`: 'single', 'multiple', or 'truefalse'\n"
            f"   - `bloom_level`: one of 'remember', 'understand', 'apply', 'analyze', 'evaluate'\n"
            f"   - `difficulty`: one of 'easy', 'medium', 'hard'\n"
            f"5. Do NOT include explanations, rationale, or markdown commentary.\n\n"
            f"=== REFERENCE CONTEXT ===\n"
            f"{combined_context}\n"
        )

        # 3. Call Gemini with structured response schema
        quiz = self._call_gemini(prompt)

        # 4. Strict question count verification & retry
        if len(quiz.questions) != target_count:
            logger.warning(
                "Gemini generated %d questions, but requested count is %d. Retrying once with corrective prompt...",
                len(quiz.questions),
                target_count,
            )
            corrective_prompt = (
                f"{prompt}\n\n"
                f"CRITICAL ERROR IN PREVIOUS ATTEMPT: You generated {len(quiz.questions)} questions. "
                f"You MUST generate EXACTLY {target_count} questions. Double-check your output count."
            )
            quiz = self._call_gemini(corrective_prompt)

            if len(quiz.questions) != target_count:
                error_msg = (
                    f"Question count mismatch: requested {target_count} questions, "
                    f"but model produced {len(quiz.questions)} questions."
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

        # A pooled request can hit the right TOTAL with the wrong mix, which the
        # count check above cannot see. Verify each bucket and retry once more.
        if pool_plan:
            short = self._buckets_short(quiz.questions, pool_plan)
            if short:
                logger.warning("Difficulty mix wrong (%s). Retrying once...", short)
                quiz = self._call_gemini(
                    f"{prompt}\n\n"
                    f"CRITICAL ERROR IN PREVIOUS ATTEMPT: the difficulty mix was wrong - {short}. "
                    f"Produce EXACTLY {pool_plan.easy} easy, {pool_plan.medium} medium and "
                    f"{pool_plan.hard} hard questions, {target_count} in total."
                )
                short = self._buckets_short(quiz.questions, pool_plan)
                if short:
                    # Not fatal. A bucket that is over-full is harmless, and the
                    # quiz engine substitutes the nearest difficulty if one runs
                    # dry, so a wrong mix degrades adaptivity instead of failing
                    # a teacher's generation outright.
                    logger.error("Difficulty mix still wrong after retry (%s) - serving anyway", short)

        # Ensure IDs are 1-indexed sequentially
        for idx, q in enumerate(quiz.questions, start=1):
            q.id = idx

        # Surface the cognitive spread. A quiz that comes back entirely
        # 'remember' says something about the retrieved context or the source
        # material rather than being a failure, so this is logged, not raised on.
        spread = Counter(q.bloom_level for q in quiz.questions)
        logger.info(
            "Bloom distribution: %s",
            ", ".join(f"{lvl}={spread[lvl]}" for lvl in BLOOM_LEVELS if spread[lvl]),
        )

        diff_spread = Counter(q.difficulty for q in quiz.questions)
        logger.info(
            "Difficulty distribution: %s",
            ", ".join(f"{d}={diff_spread[d]}" for d in DIFFICULTIES if diff_spread[d]),
        )

        return quiz.questions

    @staticmethod
    def _buckets_short(questions: list[GeneratedQuestion], plan: PoolPlan) -> str:
        """Describe any difficulty bucket with fewer questions than planned.

        Only shortfalls matter. A bucket with extra questions is harmless - the
        quiz engine simply never reaches them.
        """
        have = Counter(q.difficulty for q in questions)
        gaps = [
            f"{d}: got {have[d]}, need {plan.count_for(d)}"
            for d in DIFFICULTIES
            if have[d] < plan.count_for(d)
        ]
        return "; ".join(gaps)

    @staticmethod
    def _is_transient_error(exc: Exception) -> bool:
        """Check if an exception is a transient 503 (Unavailable) or 429 (Rate Limit)."""
        if isinstance(exc, errors.APIError):
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            if code in (503, 429) or status in ("UNAVAILABLE", "RESOURCE_EXHAUSTED"):
                return True
            msg = (getattr(exc, "message", "") or str(exc)).upper()
            if any(term in msg for term in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND")):
                return True
            return False

        err_str = str(exc).upper()
        return any(term in err_str for term in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "HIGH DEMAND"))

    def _call_gemini(self, prompt: str) -> GeneratedQuiz:
        """Execute generate_content against Google Gemini with JSON schema enforcement.

        Retries on transient 503 (Unavailable) and 429 (Rate Limit) errors using
        exponential backoff (2s, 4s, 8s) up to 3 retries. Normal validation,
        auth, or bad-request errors are NOT retried.
        """
        delays = [2.0, 4.0, 8.0]
        last_exception: Exception | None = None

        for attempt in range(len(delays) + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.config.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=self.config.temperature,
                        response_mime_type="application/json",
                        response_schema=GeneratedQuiz,
                    ),
                )

                if response.parsed and isinstance(response.parsed, GeneratedQuiz):
                    return response.parsed

                # Fallback to direct Pydantic JSON parsing
                if response.text:
                    return GeneratedQuiz.model_validate_json(response.text)

                raise RuntimeError("Empty or unparseable response from Gemini generation API.")

            except Exception as exc:
                if not self._is_transient_error(exc):
                    # Do not retry validation, auth, or client bad-request errors
                    raise

                last_exception = exc
                if attempt < len(delays):
                    delay = delays[attempt]
                    logger.warning(
                        "Gemini API transient error on attempt %d/%d: %s. Retrying in %.1fs...",
                        attempt + 1,
                        len(delays),
                        exc,
                        delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "Gemini API transient error persisted after %d retries: %s",
                        len(delays),
                        exc,
                    )

        raise RuntimeError(
            "Gemini AI generation service is temporarily unavailable due to high demand. "
            "Please try again in a few moments."
        ) from last_exception
