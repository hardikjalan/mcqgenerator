'use client'

import { RotateCcw, ArrowLeft } from 'lucide-react'
import type { AttemptResult } from '@/types/quiz'
import { DIFFICULTY_BY_KEY } from '@/lib/quiz-config'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

type QuizResultProps = {
  result: AttemptResult
  onRetake: () => void
  onBack: () => void
}

/**
 * The end of an attempt.
 *
 * Shows the score next to the level the student settled at, because with
 * adaptive difficulty the score alone does not say much: 7/10 reached while
 * answering hard questions is a different result from 7/10 spent on easy ones.
 */
export function QuizResult({ result, onRetake, onBack }: QuizResultProps) {
  const settled = DIFFICULTY_BY_KEY[result.settled_difficulty]
  const pct = result.total > 0 ? Math.round((result.score / result.total) * 100) : 0

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-4">
      <Card className="p-6 flex flex-col items-center text-center gap-2">
        <span className="text-xs text-text-3">{result.subject || 'Quiz'} — finished</span>
        <p className="text-4xl font-bold text-text tabular">
          {result.score}
          <span className="text-text-3"> / {result.total}</span>
        </p>
        <p className="text-sm text-text-2 tabular">{pct}% correct</p>

        <div className="flex items-center gap-2 mt-2">
          <span className="text-xs text-text-3">Settled at</span>
          <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${settled.badge}`}>
            {settled.label}
          </span>
        </div>
        <p className="text-xs text-text-3 max-w-sm mt-1">
          The quiz moved up when you got two right in a row, and down after two wrong.
          Where it settled says more than the score on its own.
        </p>
      </Card>

      <Card className="p-5 flex flex-col gap-3">
        <h3 className="text-sm font-semibold text-text">How you did at each level</h3>
        <ul className="flex flex-col gap-2">
          {result.breakdown.map(row => {
            const meta = DIFFICULTY_BY_KEY[row.difficulty]
            const width = row.asked > 0 ? (row.correct / row.asked) * 100 : 0
            return (
              <li key={row.difficulty} className="flex items-center gap-3">
                <span className={`text-xs font-semibold px-2 py-0.5 rounded-full border w-20 text-center shrink-0 ${meta.badge}`}>
                  {meta.label}
                </span>
                <span className="flex-1 h-1.5 rounded-full bg-surface-2 overflow-hidden" aria-hidden="true">
                  <span className="block h-full bg-accent" style={{ width: `${width}%` }} />
                </span>
                <span className="text-xs text-text-2 tabular shrink-0 w-14 text-right">
                  {row.correct} / {row.asked}
                </span>
              </li>
            )
          })}
        </ul>
      </Card>

      <div className="flex items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="w-3.5 h-3.5" aria-hidden="true" />
          All quizzes
        </Button>
        <Button variant="secondary" size="md" onClick={onRetake}>
          <RotateCcw className="w-4 h-4" aria-hidden="true" />
          Take it again
        </Button>
      </div>
    </div>
  )
}
