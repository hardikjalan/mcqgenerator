/**
 * types/quiz.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Types describing an assessment and how it is configured.
 *
 * Shared by both sides of the product: faculty build a QuizConfig here, and the
 * student player reads the same QuestionType values when rendering a quiz.
 *
 * Runtime option lists (labels, icons, presets) live in @/lib/quiz-config
 */

export type QuestionType = 'single' | 'multiple' | 'truefalse' | 'all'

export type QuizConfig = {
  subjectName: string
  topicsCovered: string
  learningObjective: string
  gradeLevel: string
  questionType: QuestionType
  questionCount: number
  customCount: string
  timeLimit: string
}

/**
 * Bloom's taxonomy levels, in increasing order of cognitive demand.
 *
 * Mirrors BloomLevel in backend/app/services/rag/generation/models.py — change
 * both together. 'create' is absent on purpose: it requires the student to
 * produce something original, which multiple choice cannot assess.
 */
export type BloomLevel = 'remember' | 'understand' | 'apply' | 'analyze' | 'evaluate'

export type GeneratedQuestion = {
  id: number
  question: string
  options: string[]
  correct_answer: string | string[]
  question_type?: string
  /** Optional so a response from a backend without tagging still type-checks. */
  bloom_level?: BloomLevel
}

// ── Taking a quiz ────────────────────────────────────────────────────────────
// These mirror the response models in backend/app/schemas.py. Note what is NOT
// here: no correct_answer on a question. The backend serves one question at a
// time with the key stripped and grades server-side, so the browser never holds
// the answers — see backend/app/services/quiz_session.py.

export type Difficulty = 'easy' | 'medium' | 'hard'

export type QuizSummary = {
  id: string
  subject: string
  topics: string
  grade_level: string
  quiz_length: number
  created_at: string
}

export type PublicQuestion = {
  id: number
  question: string
  options: string[]
  question_type: string
  difficulty: Difficulty
  /** 1-based position in the quiz, and how many questions it has. */
  number: number
  total: number
}

/** Returned only AFTER an answer is submitted, so the key is no longer secret. */
export type AnswerFeedback = {
  was_correct: boolean
  correct_answer: string | string[]
  difficulty: Difficulty
}

export type SubmitAnswerResponse = {
  feedback: AnswerFeedback
  question: PublicQuestion | null
  finished: boolean
}

export type AttemptResult = {
  attempt_id: string
  quiz_id: string
  subject: string
  score: number
  total: number
  /** Where the ladder settled — a raw score alone is misleading when the
      difficulty moved during the quiz. */
  settled_difficulty: Difficulty
  breakdown: { difficulty: Difficulty; asked: number; correct: number }[]
}
