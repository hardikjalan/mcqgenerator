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
export type BloomLevel = 'Remember' | 'Understand' | 'Apply' | 'Analyze' | 'Evaluate' | 'Create'

export type QuizConfig = {
  subjectName: string
  topicsCovered: string
  learningObjective: string
  gradeLevel: string
  questionType: QuestionType
  questionCount: number
  customCount: string
  timeLimit: string
  bloomLevels?: BloomLevel[]
  adaptive?: boolean
}

export type GeneratedQuestion = {
  id: number
  question: string
  options: string[]
  correct_answer: string | string[]
  question_type: 'single' | 'multiple' | 'truefalse'
  explanation: string
  evidence: Evidence[]
  bloom_level: BloomLevel
  bloom_rationale: string
  difficulty: number
  topic: string
}

export type Evidence = {
  source_id: string
  parent_id: string
  quote: string
  file_name: string
  page: number | null
  pages: number[]
}

