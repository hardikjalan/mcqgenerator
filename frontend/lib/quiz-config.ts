// Assessment option lists shown in the builder UI.
// Types live in @/types/quiz

import type { BloomLevel, QuestionType } from '@/types/quiz'

export const QUESTION_COUNTS = [5, 10, 15, 20]

export const QUESTION_TYPES: { key: QuestionType; label: string; desc: string; icon: string }[] = [
  { key: 'single',    label: 'Single Correct',   desc: 'One right answer',   icon: '◉' },
  { key: 'multiple',  label: 'Multiple Correct',  desc: 'Many right answers', icon: '☑' },
  { key: 'truefalse', label: 'True / False',      desc: 'Binary choice',      icon: '⇌' },
  { key: 'all',       label: 'All Types',         desc: 'Mix of all above',   icon: '⊞' },
]

// Bloom's levels in increasing order of cognitive demand. The results summary
// iterates this array, so keep the order ascending.
//
// `higherOrder` splits the five into the two groups worth telling apart at a
// glance — recall-and-explain versus genuine reasoning. It drives the badge
// colour: a five-colour scale would need five new token sets in globals.css and
// would run into the red/green reserved for right and wrong answers.
export const BLOOM_LEVELS: { key: BloomLevel; label: string; higherOrder: boolean }[] = [
  { key: 'remember',   label: 'Remember',   higherOrder: false },
  { key: 'understand', label: 'Understand', higherOrder: false },
  { key: 'apply',      label: 'Apply',      higherOrder: true  },
  { key: 'analyze',    label: 'Analyze',    higherOrder: true  },
  { key: 'evaluate',   label: 'Evaluate',   higherOrder: true  },
]

export const BLOOM_BY_KEY = Object.fromEntries(
  BLOOM_LEVELS.map(l => [l.key, l]),
) as Record<BloomLevel, (typeof BLOOM_LEVELS)[number]>
