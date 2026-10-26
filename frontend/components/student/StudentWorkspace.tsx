'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { apiRequest, errorMessage } from '@/lib/api'
import { remainingSeconds, serverClockOffset } from '@/lib/assessment-clock'
import type { AssessmentSummary, Attempt, ProgressEntry } from '@/types/assessment'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'
import { Field, FormInput } from '@/components/ui/form-fields'
import { AssessmentFeedback } from '@/components/shared/AssessmentFeedback'

export function StudentWorkspace({ mode }: { mode: 'quizzes' | 'completed' | 'progress' }) {
  const [quizzes, setQuizzes] = useState<AssessmentSummary[]>([])
  const [progress, setProgress] = useState<ProgressEntry[]>([])
  const [attempt, setAttempt] = useState<Attempt | null>(null)
  const [serverOffset, setServerOffset] = useState(0)
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [revision, setRevision] = useState(0)
  const [catalogTime, setCatalogTime] = useState(() => Date.now())
  useEffect(() => { const timer = setInterval(() => setCatalogTime(Date.now()), 30000); return () => clearInterval(timer) }, [])
  useEffect(() => {
    let cancelled = false
    Promise.all([apiRequest<AssessmentSummary[]>('/student/assessments'), apiRequest<ProgressEntry[]>('/student/progress')])
      .then(([a, b]) => { if (!cancelled) { setQuizzes(a); setProgress(b); setLoaded(true) } })
      .catch(e => { if (!cancelled) { setError(errorMessage(e)); setLoaded(true) } })
    return () => { cancelled = true }
  }, [revision])
  const join = async () => {
    setBusy(true); setError('')
    try { await apiRequest('/student/join', { method: 'POST', body: JSON.stringify({ code: code.trim() }) }); setCode(''); setRevision(n => n + 1) }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const changed = useCallback((value: Attempt) => {
    setServerOffset(serverClockOffset(value.server_time, Date.now()))
    setAttempt(value)
    if (value.status === 'submitted') setRevision(n => n + 1)
  }, [])
  const start = async (id: string) => {
    setBusy(true); setError('')
    try { changed(await apiRequest<Attempt>(`/student/assessments/${id}/start`, { method: 'POST' })) }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  if (attempt && mode === 'quizzes') return <QuizPlayer key={`${attempt.id}:${attempt.question?.id ?? 'complete'}`} attempt={attempt} serverOffset={serverOffset} onChange={changed} onBack={() => { setAttempt(null); setRevision(n => n + 1) }} />
  return <div className="max-w-4xl mx-auto flex flex-col gap-5">
    {error && <Alert>{error}</Alert>}
    {!loaded && <p role="status" className="text-text-3">Loading your assessments…</p>}
    {mode === 'quizzes' && <Card><CardHeader title="Join a quiz" hint="Your teacher will give you a join code." />
      <form onSubmit={e => { e.preventDefault(); void join() }} className="flex flex-wrap gap-3 items-end">
        <div className="flex-1 min-w-0"><Field id="join-code" label="Quiz code"><FormInput id="join-code" placeholder="Enter your code" value={code} onChange={setCode} /></Field></div>
        <Button type="submit" disabled={!code.trim()} loading={busy}>Join quiz</Button>
      </form>
    </Card>}
    {mode === 'progress' ? <>
      <Card><CardHeader title="Your progress" hint="Scores and mastery estimates come from completed assessments." />
        {!progress.length ? <p className="text-sm text-text-3">Complete an assessment to see progress.</p> : <div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr><th className="py-2">Assessment</th><th>Score</th><th>Completed</th></tr></thead><tbody>{progress.map(item => <tr key={item.id} className="border-t border-border-subtle"><td className="py-3 pr-3">{item.title}</td><td className="pr-3 tabular">{item.score}/{item.total} ({Math.round(100 * item.score / item.total)}%)</td><td className="text-text-3">{new Date(item.submitted_at).toLocaleDateString()}</td></tr>)}</tbody></table></div>}
      </Card>
      {progress[0] && <AssessmentFeedback feedback={progress[0].feedback} />}
    </> : <>
      {loaded && !quizzes.filter(q => mode === 'completed' ? q.attempt?.status === 'submitted' : true).length && <Card><p className="text-text-2">{mode === 'completed' ? 'No completed assessments yet.' : 'Join a quiz using the code from your teacher.'}</p></Card>}
      {quizzes.filter(q => mode === 'completed' ? q.attempt?.status === 'submitted' : true).map(quiz => <Card key={quiz.id}><div className="flex flex-wrap justify-between gap-4 items-center">
        <div><h2 className="text-lg font-bold">{quiz.title}</h2><p className="text-sm text-text-3 mt-1">{quiz.question_count} questions · {quiz.duration_seconds ? `${quiz.duration_seconds / 60} minutes` : 'No time limit'} · {quiz.adaptive ? 'Adaptive sequence' : 'Fixed sequence'}</p>
          {quiz.closes_at && <p className="text-xs text-text-3 mt-1">Closes {new Date(quiz.closes_at).toLocaleString()}</p>}
          {quiz.attempt?.status === 'submitted' && <p className="text-success text-sm mt-2">Score: {quiz.attempt.score}/{quiz.attempt.total}</p>}
        </div>
        <Button loading={busy} disabled={!quiz.attempt && (quiz.status !== 'published' || Boolean(quiz.closes_at && new Date(quiz.closes_at).getTime() <= catalogTime))} onClick={() => start(quiz.id)}>{quiz.attempt?.status === 'submitted' ? 'Review results' : quiz.attempt ? 'Resume quiz' : 'Start quiz'}</Button>
      </div></Card>)}
    </>}
    {mode === 'completed' && attempt?.feedback && <AssessmentFeedback feedback={attempt.feedback} />}
  </div>
}

function QuizPlayer({ attempt, serverOffset, onChange, onBack }: { attempt: Attempt; serverOffset: number; onChange: (value: Attempt) => void; onBack: () => void }) {
  const [choices, setChoices] = useState<number[]>(attempt.draft_answers ?? [])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [saved, setSaved] = useState(false)
  const [clock, setClock] = useState(() => Date.now())
  const dialog = useRef<HTMLDialogElement>(null)
  const timedOut = useRef(false)
  const remaining = remainingSeconds(attempt.expires_at, clock, serverOffset)
  const finish = useCallback(async () => {
    setBusy(true); setError('')
    try { onChange(await apiRequest<Attempt>(`/student/attempts/${attempt.id}/finish`, { method: 'POST', body: JSON.stringify({ version: attempt.version }) })) }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false); dialog.current?.close() }
  }, [attempt.id, attempt.version, onChange])
  useEffect(() => { const timer = setInterval(() => setClock(Date.now()), 1000); return () => clearInterval(timer) }, [])
  useEffect(() => {
    if (remaining === 0 && attempt.status === 'active' && !busy && !timedOut.current) { timedOut.current = true; void finish() }
  }, [remaining, attempt.status, busy, finish])
  const select = async (index: number) => {
    if (busy || remaining === 0 || !attempt.question) return
    const previous = choices
    const next = attempt.question.question_type === 'multiple' ? choices.includes(index) ? choices.filter(i => i !== index) : [...choices, index] : [index]
    setChoices(next); setBusy(true); setError(''); setSaved(false)
    try {
      onChange(await apiRequest<Attempt>(`/student/attempts/${attempt.id}/answer`, { method: 'POST', body: JSON.stringify({ version: attempt.version, question_id: attempt.question.id, choices: next, draft: true }) }))
      setSaved(true)
    } catch (e) { setChoices(previous); setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const submit = async () => {
    if (!attempt.question || busy) return
    setBusy(true); setError('')
    try { onChange(await apiRequest<Attempt>(`/student/attempts/${attempt.id}/answer`, { method: 'POST', body: JSON.stringify({ version: attempt.version, question_id: attempt.question.id, choices }) })) }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  if (attempt.status === 'submitted') return <div className="max-w-4xl mx-auto flex flex-col gap-5">
    <Card><CardHeader title={attempt.title} /><p className="text-3xl font-bold tabular">{attempt.score}/{attempt.total}</p><p className="text-sm text-text-2 mt-2">Assessment submitted. Unanswered questions count as incorrect.</p><Button variant="secondary" className="mt-4" onClick={onBack}>Back to quizzes</Button></Card>
    {attempt.feedback && <AssessmentFeedback feedback={attempt.feedback} />}
  </div>
  return <div className="max-w-3xl mx-auto flex flex-col gap-5">
    <div className="flex flex-wrap gap-3 justify-between items-center"><Button variant="ghost" size="sm" onClick={onBack}>Back to quizzes</Button><span className="text-sm text-text-3">{attempt.answered}/{attempt.total} answered</span>{remaining !== null && <span role="timer" aria-label="Time remaining" className={`font-mono font-bold tabular ${remaining < 60 ? 'text-danger' : 'text-text'}`}>{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, '0')}</span>}</div>
    <progress className="w-full accent-accent" value={attempt.answered} max={attempt.total} aria-label="Answered questions" />
    {error && <Alert>{error} <button className="underline cursor-pointer" onClick={async () => { try { const fresh = await apiRequest<Attempt>(`/student/attempts/${attempt.id}`); setChoices(fresh.draft_answers ?? []); timedOut.current = false; onChange(fresh); setError('') } catch (e) { setError(errorMessage(e)) } }}>Reload attempt</button></Alert>}
    {remaining === 0 && <Alert tone="warning">Time is up. Your committed responses will be submitted. {error && <Button size="sm" onClick={finish}>Retry submission</Button>}</Alert>}
    {attempt.question && <Card><CardHeader title={attempt.title} hint={attempt.adaptive ? 'Question order adapts to your responses and topic coverage.' : 'Answer each question before continuing.'} />
      <fieldset disabled={busy || remaining === 0}>
        <legend className="text-lg font-semibold mb-4">{attempt.answered + 1}. {attempt.question.question}</legend>
        {attempt.question.question_type === 'multiple' && <p className="text-sm text-text-3 mb-3">Select all correct answers.</p>}
        <div className="flex flex-col gap-3">{attempt.question.options.map((option, index) => <label key={index} className={`flex gap-3 items-start border rounded-md p-4 cursor-pointer ${choices.includes(index) ? 'border-accent bg-accent-soft' : 'border-border-strong bg-surface'}`}>
          <input type={attempt.question?.question_type === 'multiple' ? 'checkbox' : 'radio'} name="quiz-answer" checked={choices.includes(index)} onChange={() => select(index)} className="accent-accent mt-1" /><span className="text-base break-words">{option}</span>
        </label>)}</div>
      </fieldset>
      <p role="status" className="text-xs text-text-3 mt-3">{busy ? 'Saving…' : saved ? 'Answer saved. Submit it to continue.' : 'Your selection is saved automatically.'}</p>
      <div className="flex flex-wrap gap-3 mt-5 justify-between"><Button variant="secondary" disabled={busy} onClick={() => dialog.current?.showModal()}>Finish assessment</Button><Button disabled={!choices.length || remaining === 0} loading={busy} onClick={submit}>{attempt.answered + 1 === attempt.total ? 'Submit final answer' : 'Submit answer and continue'}</Button></div>
    </Card>}
    <dialog ref={dialog} className="bg-surface text-text border border-border-strong rounded-xl p-6 max-w-md backdrop:bg-text/40">
      <h2 className="text-xl font-bold">Submit this assessment?</h2><p className="text-sm text-text-2 mt-3">{attempt.total - attempt.answered} questions are not committed yet. Draft selections and unanswered questions count as incorrect. You cannot restart after submitting.</p><div className="flex gap-3 mt-5"><Button variant="secondary" onClick={() => dialog.current?.close()}>Keep working</Button><Button loading={busy} onClick={finish}>Submit assessment</Button></div>
    </dialog>
  </div>
}
