'use client'

import { useState } from 'react'
import { CheckCircle2, XCircle, ArrowRight } from 'lucide-react'
import type {
  AnswerFeedback,
  AttemptResult,
  PublicQuestion,
  SubmitAnswerResponse,
} from '@/types/quiz'
import { DIFFICULTY_BY_KEY } from '@/lib/quiz-config'
import { apiUrl } from '@/lib/env'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'

type QuizPlayerProps = {
  attemptId: string
  first: PublicQuestion
  onFinished: (result: AttemptResult) => void
  onQuit: () => void
}

/**
 * Plays one adaptive attempt: show a question, submit it, show whether it was
 * right, move on.
 *
 * There is no way back to a previous question, by design. The next question is
 * chosen from how this one was answered, so "back" would mean unwinding the
 * ladder and discarding a question the server has already served.
 */
export function QuizPlayer({ attemptId, first, onFinished, onQuit }: QuizPlayerProps) {
  const [question, setQuestion] = useState<PublicQuestion>(first)
  const [selected, setSelected] = useState<string[]>([])
  const [feedback, setFeedback] = useState<AnswerFeedback | null>(null)
  const [pending, setPending] = useState<PublicQuestion | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isMulti = question.question_type === 'multiple'
  const difficulty = DIFFICULTY_BY_KEY[question.difficulty]

  const toggle = (option: string) => {
    if (feedback) return // answered already; options are frozen
    setSelected(prev =>
      isMulti
        ? prev.includes(option) ? prev.filter(o => o !== option) : [...prev, option]
        : [option],
    )
  }

  const submit = async () => {
    if (selected.length === 0 || busy) return
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/attempts/${attemptId}/answer`), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selected: isMulti ? selected : selected[0] }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.error ?? `Server error: ${res.status}`)
      }
      const data: SubmitAnswerResponse = await res.json()
      setFeedback(data.feedback)
      setPending(data.question)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not submit that answer.')
    } finally {
      setBusy(false)
    }
  }

  const advance = async () => {
    if (pending) {
      setQuestion(pending)
      setPending(null)
      setFeedback(null)
      setSelected([])
      return
    }
    // No next question: the attempt is over, so fetch the result.
    setBusy(true)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/attempts/${attemptId}/result`))
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.error ?? `Server error: ${res.status}`)
      }
      onFinished(await res.json())
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not load your result.')
    } finally {
      setBusy(false)
    }
  }

  const isChosen = (option: string) => selected.includes(option)
  const isKey = (option: string) => {
    if (!feedback) return false
    const key = feedback.correct_answer
    return Array.isArray(key) ? key.includes(option) : key === option
  }

  return (
    <div className="max-w-2xl mx-auto flex flex-col gap-4">
      {/* ── Progress ──────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs text-text-3 tabular">
          Question {question.number} of {question.total}
        </span>
        <span
          className={`text-xs font-semibold px-2 py-0.5 rounded-full border ${difficulty.badge}`}
          title="This quiz adjusts difficulty as you go"
        >
          {difficulty.label}
        </span>
      </div>

      {/* Determinate on purpose: the total is known, so a real proportion is
          honest here. Nothing is being guessed or animated on a timer. */}
      <div className="h-1 rounded-full bg-surface-2 overflow-hidden" aria-hidden="true">
        <div
          className="h-full bg-accent transition-all"
          style={{ width: `${((question.number - 1) / question.total) * 100}%` }}
        />
      </div>

      <Card className="p-5 sm:p-6 flex flex-col gap-4">
        <h2 className="text-base sm:text-lg font-semibold text-text leading-relaxed">
          {question.question}
        </h2>
        {isMulti && (
          <p className="text-xs text-text-3">Select every answer that applies.</p>
        )}

        <div className="flex flex-col gap-2.5">
          {question.options.map((option, i) => {
            const chosen = isChosen(option)
            const key = isKey(option)

            // Before answering, only the student's choice is highlighted. After,
            // the key is shown in success and a wrong pick in danger.
            let tone = 'border-border-strong bg-surface text-text hover:bg-surface-2'
            if (feedback) {
              if (key) tone = 'border-success-line bg-success-soft text-success'
              else if (chosen) tone = 'border-danger-line bg-danger-soft text-danger'
              else tone = 'border-border-subtle bg-surface text-text-3'
            } else if (chosen) {
              tone = 'border-accent-line bg-accent-soft text-accent'
            }

            return (
              <button
                key={i}
                type="button"
                onClick={() => toggle(option)}
                disabled={!!feedback}
                aria-pressed={chosen}
                className={`flex items-center gap-3 px-3.5 py-3 rounded-lg border text-sm text-left transition-colors ${tone} disabled:cursor-default`}
              >
                <span className="w-6 h-6 rounded-md bg-surface-2 border border-border-subtle flex items-center justify-center text-xs font-bold shrink-0">
                  {String.fromCharCode(65 + i)}
                </span>
                <span className="flex-1">{option}</span>
                {feedback && key && <CheckCircle2 className="w-4 h-4 shrink-0" aria-hidden="true" />}
                {feedback && !key && chosen && <XCircle className="w-4 h-4 shrink-0" aria-hidden="true" />}
              </button>
            )
          })}
        </div>

        {error && <Alert tone="error">{error}</Alert>}

        {feedback && (
          <Alert tone={feedback.was_correct ? 'success' : 'error'}>
            {feedback.was_correct ? 'Correct.' : 'Not quite — the right answer is marked above.'}
          </Alert>
        )}

        <div className="flex items-center justify-between gap-3 pt-1">
          <Button variant="ghost" size="sm" onClick={onQuit} disabled={busy}>
            Leave quiz
          </Button>
          {feedback ? (
            <Button size="md" onClick={advance} loading={busy}>
              {pending ? 'Next question' : 'See result'}
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Button>
          ) : (
            <Button size="md" onClick={submit} loading={busy} disabled={selected.length === 0}>
              Submit answer
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}
