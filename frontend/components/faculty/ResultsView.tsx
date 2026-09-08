'use client'

import { ArrowLeft, CheckCircle2, FileQuestion, HelpCircle } from 'lucide-react'
import type { GeneratedQuestion, QuizConfig } from '@/types/quiz'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'

type ResultsViewProps = {
  questions: GeneratedQuestion[]
  config: QuizConfig | null
  onBackToCreate: () => void
}

export function ResultsView({ questions, config, onBackToCreate }: ResultsViewProps) {
  if (questions.length === 0) {
    return (
      <div className="max-w-4xl mx-auto py-12 flex flex-col items-center justify-center text-center">
        <div className="w-16 h-16 rounded-2xl bg-surface-2 border border-border-strong flex items-center justify-center text-text-3 mb-4">
          <FileQuestion className="w-8 h-8" />
        </div>
        <h2 className="text-xl font-bold text-text mb-2">No quiz generated yet</h2>
        <p className="text-sm text-text-3 max-w-md mb-6">
          Upload reference documents and configure your quiz parameters in the Create section to generate assessment questions.
        </p>
        <Button size="md" onClick={onBackToCreate}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Go to Create
        </Button>
      </div>
    )
  }

  const isCorrect = (optionText: string, correctAnswer: string | string[]) => {
    const opt = optionText.trim().toLowerCase()
    if (Array.isArray(correctAnswer)) {
      return correctAnswer.some(ans => ans.trim().toLowerCase() === opt)
    }
    return correctAnswer.trim().toLowerCase() === opt
  }

  const getOptionLetter = (idx: number) => {
    return String.fromCharCode(65 + idx) // A, B, C, D...
  }

  return (
    <div className="max-w-4xl mx-auto flex flex-col gap-6">
      {/* ── Top Bar / Header ────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-border-subtle">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-accent-soft text-accent border border-accent/20">
              {questions.length} Questions Generated
            </span>
            {config?.subjectName && (
              <span className="text-xs font-medium text-text-3">
                • {config.subjectName}
              </span>
            )}
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-text">Assessment Results</h2>
          {config?.topicsCovered && (
            <p className="text-xs text-text-3">
              Topics: <span className="text-text-2">{config.topicsCovered}</span>
            </p>
          )}
        </div>

        <div className="flex items-center gap-2.5">
          <Button variant="secondary" size="sm" onClick={onBackToCreate}>
            <ArrowLeft className="w-3.5 h-3.5 mr-1.5" />
            Back to Create
          </Button>
        </div>
      </div>

      {/* ── Questions List ──────────────────────────────────────────── */}
      <div className="flex flex-col gap-5">
        {questions.map((q, qIndex) => {
          const isTrueFalse = q.question_type === 'truefalse' || (q.options.length === 2 && q.options.includes('True'))
          const isMultiSelect = Array.isArray(q.correct_answer) && q.correct_answer.length > 1

          return (
            <Card key={q.id || qIndex} className="p-5 sm:p-6 transition-all border-border-strong hover:border-text-3/40">
              <div className="flex items-start justify-between gap-3 mb-3">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-bold px-2 py-0.5 rounded-md bg-accent text-surface tabular">
                    Q{qIndex + 1}
                  </span>
                  <span className="text-xs font-medium text-text-3 capitalize">
                    {isTrueFalse
                      ? 'True / False'
                      : isMultiSelect
                      ? 'Multiple Choice (Select all that apply)'
                      : 'Single Choice'}
                  </span>
                </div>
              </div>

              {/* Question text */}
              <h3 className="text-base sm:text-lg font-semibold text-text leading-relaxed mb-4">
                {q.question}
              </h3>

              {/* Options list */}
              <div className="grid grid-cols-1 gap-2.5">
                {q.options.map((opt, optIndex) => {
                  const correct = isCorrect(opt, q.correct_answer)

                  return (
                    <div
                      key={optIndex}
                      className={[
                        'flex items-center justify-between gap-3 px-3.5 py-3 rounded-lg border text-sm transition-all',
                        correct
                          ? 'border-emerald-500/50 bg-emerald-500/10 text-emerald-200 dark:text-emerald-300 font-medium'
                          : 'border-border-strong bg-surface text-text hover:bg-surface-2',
                      ].join(' ')}
                    >
                      <div className="flex items-center gap-3 min-w-0">
                        <span
                          className={[
                            'w-6 h-6 rounded-md flex items-center justify-center text-xs font-bold shrink-0',
                            correct
                              ? 'bg-emerald-500 text-slate-950'
                              : 'bg-surface-2 text-text-3 border border-border-subtle',
                          ].join(' ')}
                        >
                          {isTrueFalse ? (opt === 'True' ? 'T' : 'F') : getOptionLetter(optIndex)}
                        </span>
                        <span className="truncate break-words">{opt}</span>
                      </div>

                      {correct && (
                        <div className="flex items-center gap-1.5 shrink-0 text-xs font-semibold text-emerald-400">
                          <CheckCircle2 className="w-4 h-4" />
                          <span className="hidden sm:inline">Correct</span>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
