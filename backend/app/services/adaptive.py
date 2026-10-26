"""
adaptive.py
===========
The difficulty ladder, and the pool size it implies.

One answer is not evidence. A student who guesses a hard question right, or
slips on an easy one, has not demonstrated anything, so a single result never
moves the level. The ladder requires CONSECUTIVE agreeing results instead:

    start at 'easy'
    STEP_THRESHOLD correct in a row at the current level  -> step up
    STEP_THRESHOLD wrong   in a row at the current level  -> step down
    a mixed pair resets the run and the level stays put
    clamped at 'easy' and 'hard'

This is a symmetric staircase, so it settles around the difficulty where the
student is right about half the time. If that reads as too punishing, lowering
the step-down threshold below the step-up one shifts the settling point higher
(the classic "two up, one down" targets roughly 70% correct) -- but then
``plan_pool`` must be re-derived, because the bounds below come directly from
these rules.

Pool sizing
-----------
The question pool has to survive EVERY path a student could take, and the path
is not known in advance, so each bucket is sized for its own worst case:

    easy   = N        all wrong, or alternating: 'easy' is the floor, so the
                      student never leaves it
    medium = N - k    fastest possible arrival is k correct at 'easy'
    hard   = N - 2k   fastest possible arrival is k at 'easy' then k at 'medium'

with k = STEP_THRESHOLD. These are independent maxima, not one path, which is
why they are summed rather than maximised over.
"""

from __future__ import annotations

from typing import Literal, get_args

from pydantic import BaseModel, Field

Difficulty = Literal["easy", "medium", "hard"]

# Ascending order of difficulty. Derived from the Literal so the two cannot drift.
DIFFICULTIES: tuple[Difficulty, ...] = get_args(Difficulty)

# Consecutive agreeing answers needed before the level moves.
# Changing this changes the pool bounds -- see the module docstring.
STEP_THRESHOLD = 2

START_DIFFICULTY: Difficulty = "easy"


class PoolPlan(BaseModel):
    """How many questions of each difficulty an adaptive quiz must have."""

    quiz_length: int
    easy: int
    medium: int
    hard: int

    @property
    def total(self) -> int:
        return self.easy + self.medium + self.hard

    def count_for(self, difficulty: Difficulty) -> int:
        return getattr(self, difficulty)

    def as_dict(self) -> dict[str, int]:
        return {"easy": self.easy, "medium": self.medium, "hard": self.hard}


def plan_pool(quiz_length: int, step_threshold: int = STEP_THRESHOLD) -> PoolPlan:
    """
    Size each difficulty bucket so no answer path can exhaust it.

    Every bucket keeps a floor of 1. A short quiz can never climb to 'hard'
    (N <= 2k makes the bound zero or negative), but generating one anyway costs
    a single question and means the pool is still valid if the ladder rules are
    later loosened.
    """
    if quiz_length < 1:
        raise ValueError("quiz_length must be at least 1")

    return PoolPlan(
        quiz_length=quiz_length,
        easy=max(quiz_length, 1),
        medium=max(quiz_length - step_threshold, 1),
        hard=max(quiz_length - 2 * step_threshold, 1),
    )


class LadderState(BaseModel):
    """Where a single attempt currently sits on the ladder."""

    difficulty: Difficulty = START_DIFFICULTY
    # Length of the current run and whether it is a run of correct answers.
    run_length: int = 0
    run_is_correct: bool = False

    def record(self, was_correct: bool, step_threshold: int = STEP_THRESHOLD) -> "LadderState":
        """
        Fold one answer into the ladder and return the resulting state.

        Returns a new object rather than mutating, so a caller can keep the
        previous state for logging or for showing the student why the level
        moved.
        """
        if self.run_length > 0 and self.run_is_correct == was_correct:
            run_length = self.run_length + 1
        else:
            run_length = 1

        difficulty = self.difficulty
        if run_length >= step_threshold:
            idx = DIFFICULTIES.index(difficulty)
            idx = min(idx + 1, len(DIFFICULTIES) - 1) if was_correct else max(idx - 1, 0)
            moved_to = DIFFICULTIES[idx]
            if moved_to != difficulty:
                # The run has done its work; start counting again at the new level.
                return LadderState(difficulty=moved_to, run_length=0, run_is_correct=was_correct)
            # Already clamped at an end of the ladder. Keep the run so the next
            # answer is still judged against a run, not treated as a fresh start.
            return LadderState(difficulty=difficulty, run_length=run_length, run_is_correct=was_correct)

        return LadderState(difficulty=difficulty, run_length=run_length, run_is_correct=was_correct)
