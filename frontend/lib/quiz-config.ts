// Assessment option lists shown in the builder UI.
// Types live in @/types/quiz

import type { QuestionType } from '@/types/quiz'

export const QUESTION_COUNTS = [5, 10, 15, 20]

export const QUESTION_TYPES: { key: QuestionType; label: string; desc: string; icon: string }[] = [
  { key: 'single',    label: 'Single Correct',   desc: 'One right answer',   icon: '◉' },
  { key: 'multiple',  label: 'Multiple Correct',  desc: 'Many right answers', icon: '☑' },
  { key: 'truefalse', label: 'True / False',      desc: 'Binary choice',      icon: '⇌' },
  { key: 'all',       label: 'All Types',         desc: 'Mix of all above',   icon: '⊞' },
]
