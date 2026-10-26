'use client'

import { useCallback, useEffect, useState } from 'react'
import { BookOpen, CheckCircle2, TrendingUp, RefreshCw } from 'lucide-react'
import { AppShell, type NavItem } from '@/components/shared/AppShell'
import { Card } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'
import { Spinner } from '@/components/ui/Spinner'
import { QuizPlayer } from '@/components/student/QuizPlayer'
import { QuizResult } from '@/components/student/QuizResult'
import { apiUrl } from '@/lib/env'
import type { AttemptResult, PublicQuestion, QuizSummary } from '@/types/quiz'

const NAV: NavItem[] = [
  { label: 'My quizzes', href: '/dashboard/student', Icon: BookOpen },
  { label: 'Completed',  Icon: CheckCircle2 },
  { label: 'Progress',   Icon: TrendingUp },
]

type Stage =
  | { name: 'list' }
  | { name: 'playing'; quizId: string; attemptId: string; first: PublicQuestion }
  | { name: 'result'; quizId: string; result: AttemptResult }

/** Fetch with no state of its own, so both the first load and Refresh share it. */
async function fetchQuizzes(): Promise<QuizSummary[]> {
  const res = await fetch(apiUrl('/quizzes'))
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body.error ?? `Server error: ${res.status}`)
  }
  return res.json()
}

const reachError = (err: unknown, fallback: string) =>
  err instanceof Error ? err.message : fallback

export default function StudentDashboard() {
  const [quizzes, setQuizzes] = useState<QuizSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [startingId, setStartingId] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage>({ name: 'list' })

  const loadQuizzes = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setQuizzes(await fetchQuizzes())
    } catch (err: unknown) {
      setError(reachError(err, 'Couldn’t reach the server. Is the backend running?'))
    } finally {
      setLoading(false)
    }
  }, [])

  // The first load deliberately does not go through loadQuizzes: that sets
  // state synchronously, which in an effect causes a cascading render. `loading`
  // already starts true, so there is nothing to set before the fetch resolves.
  // The cancelled flag stops a late response writing to an unmounted component.
  useEffect(() => {
    let cancelled = false
    fetchQuizzes()
      .then(qs => { if (!cancelled) setQuizzes(qs) })
      .catch((err: unknown) => {
        if (!cancelled) setError(reachError(err, 'Couldn’t reach the server. Is the backend running?'))
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  const startQuiz = async (quizId: string) => {
    setStartingId(quizId)
    setError(null)
    try {
      const res = await fetch(apiUrl(`/quizzes/${quizId}/attempts`), { method: 'POST' })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.error ?? `Server error: ${res.status}`)
      }
      const data = await res.json()
      setStage({
        name: 'playing',
        quizId,
        attemptId: data.attempt_id,
        first: data.question,
      })
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not start that quiz.')
    } finally {
      setStartingId(null)
    }
  }

  const backToList = () => {
    setStage({ name: 'list' })
    void loadQuizzes()
  }

  // ── Playing / result take over the whole screen ───────────────────────────
  if (stage.name === 'playing') {
    return (
      <AppShell nav={NAV} roleLabel="Student" title="Quiz">
        <QuizPlayer
          attemptId={stage.attemptId}
          first={stage.first}
          onFinished={result => setStage({ name: 'result', quizId: stage.quizId, result })}
          onQuit={backToList}
        />
      </AppShell>
    )
  }

  if (stage.name === 'result') {
    return (
      <AppShell nav={NAV} roleLabel="Student" title="Your result">
        <QuizResult
          result={stage.result}
          onRetake={() => void startQuiz(stage.quizId)}
          onBack={backToList}
        />
      </AppShell>
    )
  }

  // ── List ──────────────────────────────────────────────────────────────────
  return (
    <AppShell nav={NAV} roleLabel="Student" title="My quizzes">
      <div className="max-w-3xl mx-auto flex flex-col gap-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs text-text-3">
            {loading ? 'Looking for quizzes…' : `${quizzes.length} available`}
          </p>
          <Button variant="ghost" size="sm" onClick={() => void loadQuizzes()} disabled={loading}>
            <RefreshCw className="w-3.5 h-3.5" aria-hidden="true" />
            Refresh
          </Button>
        </div>

        {error && <Alert tone="error">{error}</Alert>}

        {loading && (
          <Card className="flex items-center justify-center gap-2 py-12 text-text-3">
            <Spinner size={16} />
            <span className="text-sm">Loading…</span>
          </Card>
        )}

        {!loading && quizzes.length === 0 && !error && (
          <Card className="flex flex-col items-center text-center gap-3 py-14">
            <span className="w-11 h-11 rounded-lg bg-accent-soft border border-accent-line text-accent flex items-center justify-center">
              <BookOpen className="w-5 h-5" aria-hidden="true" />
            </span>
            <h2 className="text-lg font-bold text-text">No quizzes yet</h2>
            <p className="text-base text-text-2 max-w-sm">
              When a teacher generates a quiz it’ll appear here straight away.
            </p>
          </Card>
        )}

        {!loading && quizzes.map(quiz => (
          <Card key={quiz.id} className="p-5 flex flex-col sm:flex-row sm:items-center gap-4">
            <div className="flex flex-col gap-1 min-w-0 flex-1">
              <h2 className="text-base font-semibold text-text truncate">
                {quiz.subject || 'Untitled quiz'}
              </h2>
              {quiz.topics && (
                <p className="text-xs text-text-3 truncate">{quiz.topics}</p>
              )}
              <p className="text-xs text-text-3 tabular">
                {quiz.quiz_length} questions · adapts as you go
                {quiz.grade_level ? ` · ${quiz.grade_level}` : ''}
              </p>
            </div>
            <Button
              size="md"
              onClick={() => void startQuiz(quiz.id)}
              loading={startingId === quiz.id}
              disabled={startingId !== null}
            >
              Start quiz
            </Button>
          </Card>
        ))}
      </div>
    </AppShell>
  )
}
