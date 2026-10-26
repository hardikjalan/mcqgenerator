import type { GeneratedQuestion, QuizConfig, Evidence } from './quiz'

export type AssessmentSummary = {
  id: string; title: string; status: 'draft' | 'published' | 'archived'
  adaptive: boolean; duration_seconds: number | null; closes_at: string | null
  created_at: string; published_at: string | null; question_count: number; subject: string
  join_code?: string; version?: number
  attempt?: { id: string; status: 'active' | 'submitted'; score: number | null; total: number } | null
}
export type Assessment = {
  id: string; owner_id: string; title: string; config: QuizConfig; questions: GeneratedQuestion[]
  status: 'draft' | 'published' | 'archived'; join_code: string; adaptive: boolean
  duration_seconds: number | null; closes_at: string | null; version: number
}
export type Accuracy = { correct: number; total: number }
export type Feedback = {
  topics: Record<string, Accuracy>
  mastery: Record<string, { probability: number; observations: number }>
  recommendations: { topic: string; message: string; sources: Evidence[] }[]
  questions: (GeneratedQuestion & { selected: number[]; correct: boolean })[]
  mastery_method: string
}
export type Attempt = {
  id: string; assessment_id: string; title: string; status: 'active' | 'submitted'
  started_at: string; expires_at: string | null; submitted_at: string | null
  version: number; total: number; score: number | null; answered: number; adaptive: boolean
  server_time: string; draft_answers?: number[]
  question: Pick<GeneratedQuestion, 'id' | 'question' | 'options' | 'question_type'> | null
  feedback?: Feedback
}
export type Analytics = {
  assessment: AssessmentSummary; started: number; completed: number; average_percent: number | null
  topics: Record<string, Accuracy>; bloom_levels: Record<string, Accuracy>
  students: { attempt_id: string; name: string; email: string; status: string; score: number | null; total: number; submitted_at: string | null }[]
}
export type ProgressEntry = { id: string; title: string; score: number; total: number; submitted_at: string; feedback: Feedback }
