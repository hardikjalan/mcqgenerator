'use client'

import { useCallback, useEffect, useState } from 'react'
import { apiRequest, errorMessage } from '@/lib/api'
import { BLOOM_LEVELS } from '@/lib/quiz-config'
import type { Assessment, AssessmentSummary, Analytics } from '@/types/assessment'
import type { GeneratedQuestion, BloomLevel } from '@/types/quiz'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'
import { Field, FormInput } from '@/components/ui/form-fields'
import { SourceQuote, AccuracyTable } from './AssessmentFeedback'

function download(name: string, contents: string, type: string) {
  const url = URL.createObjectURL(new Blob([contents], { type }))
  const link = document.createElement('a')
  link.href = url; link.download = name; link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function AssessmentWorkspace() {
  const [items, setItems] = useState<AssessmentSummary[]>([])
  const [selected, setSelected] = useState<string | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const load = useCallback(() => {
    apiRequest<AssessmentSummary[]>('/assessments').then(value => { setItems(value); setError('') }).catch(e => setError(errorMessage(e))).finally(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])
  if (selected) return <AssessmentDetail key={selected} id={selected} onBack={() => { setSelected(null); load() }} />
  return <div className="max-w-5xl mx-auto flex flex-col gap-4">
    <div className="flex items-center justify-between gap-3"><p className="text-sm text-text-2">Review drafts, share published quizzes and inspect student results.</p><Button variant="secondary" size="sm" onClick={load}>Refresh</Button></div>
    {error && <Alert>{error}</Alert>}
    {loading && <p role="status" className="text-text-3">Loading assessments…</p>}
    {!loading && !items.length && <Card><p className="text-text-2">No assessments yet. Generate questions in Create to save your first draft.</p></Card>}
    {items.map(item => <Card key={item.id}><div className="flex flex-wrap justify-between items-center gap-4">
      <div><h2 className="font-bold text-lg">{item.title}</h2><p className="text-sm text-text-3 capitalize">{item.status} · {item.question_count} questions · {item.adaptive ? 'Adaptive sequence' : 'Fixed sequence'}</p>
        {item.status === 'published' && <p className="text-sm mt-2">Join code: <strong className="font-mono text-accent">{item.join_code}</strong></p>}</div>
      <Button variant="secondary" onClick={() => setSelected(item.id)}>{item.status === 'draft' ? 'Review draft' : 'Open assessment'}</Button>
    </div></Card>)}
  </div>
}

export function AssessmentDetail({ id, onBack }: { id: string; onBack: () => void }) {
  const [quiz, setQuiz] = useState<Assessment | null>(null)
  const [questions, setQuestions] = useState<GeneratedQuestion[]>([])
  const [title, setTitle] = useState('')
  const [closing, setClosing] = useState('')
  const [dirty, setDirty] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [showAnalytics, setShowAnalytics] = useState(false)
  const apply = useCallback((value: Assessment) => { setQuiz(value); setQuestions(value.questions); setTitle(value.title); setDirty(false) }, [])
  useEffect(() => { apiRequest<Assessment>(`/assessments/${id}`).then(apply).catch(e => setError(errorMessage(e))) }, [id, apply])
  const change = (index: number, patch: Partial<GeneratedQuestion>) => {
    setQuestions(previous => previous.map((q, i) => i === index ? { ...q, ...patch } : q)); setDirty(true); setNotice('')
  }
  const action = async (kind: 'save' | 'publish' | 'close') => {
    if (!quiz || busy) return
    setBusy(true); setError(''); setNotice('')
    try {
      let value: Assessment
      if (kind === 'save') value = await apiRequest(`/assessments/${id}`, { method: 'PATCH', body: JSON.stringify({ version: quiz.version, title, questions }) }, 300000)
      else if (kind === 'publish') value = await apiRequest(`/assessments/${id}/publish`, { method: 'POST', body: JSON.stringify({ version: quiz.version, closes_at: closing ? new Date(closing).toISOString() : null }) })
      else value = await apiRequest(`/assessments/${id}/close`, { method: 'POST' })
      apply(value); setNotice(kind === 'save' ? 'Changes saved and checked against the sources.' : kind === 'publish' ? 'Published. Share the join code with your students.' : 'Closed to new attempts.')
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  const copyCode = async () => {
    try { await navigator.clipboard.writeText(quiz?.join_code ?? ''); setNotice('Join code copied.') } catch { setNotice('Copy the join code shown below.') }
  }
  if (!quiz) return <div className="max-w-4xl mx-auto">{error ? <Alert>{error}</Alert> : <p role="status">Loading assessment…</p>}<Button variant="ghost" className="mt-4" onClick={onBack}>Back</Button></div>
  const editable = quiz.status === 'draft'
  return <div className="max-w-5xl mx-auto flex flex-col gap-5">
    <div className="flex flex-wrap gap-3 items-center justify-between"><Button variant="ghost" onClick={onBack}>Back</Button><span className="text-sm capitalize text-text-3">{quiz.status}{dirty ? ' · Unsaved changes' : ''}</span></div>
    <Card>
      {editable ? <Field id="assessment-title" label="Assessment title"><FormInput id="assessment-title" placeholder="Assessment title" value={title} onChange={value => { setTitle(value); setDirty(true) }} /></Field> : <h2 className="text-xl font-bold">{quiz.title}</h2>}
      <p className="mt-3 text-sm text-text-2">{questions.length} questions · {quiz.adaptive ? 'Adaptive ordering' : 'Fixed ordering'} · {quiz.duration_seconds ? `${quiz.duration_seconds / 60} minutes` : 'No time limit'}</p>
      {quiz.status === 'published' && <div className="mt-4 flex flex-wrap gap-3 items-center"><span>Join code: <strong className="font-mono text-accent text-xl">{quiz.join_code}</strong></span><Button size="sm" variant="secondary" onClick={copyCode}>Copy code</Button></div>}
      {editable && <div className="mt-4"><Field id="quiz-closes" label="Close new attempts at (optional)" hint="Uses your local timezone. The server enforces this deadline."><input id="quiz-closes" type="datetime-local" value={closing} onChange={e => setClosing(e.target.value)} className="bg-surface-2 border border-border-strong rounded-md p-2 text-base" /></Field></div>}
      <div className="mt-5 flex flex-wrap gap-2">
        {editable && <><Button variant="secondary" disabled={!dirty} loading={busy} onClick={() => action('save')}>Save changes</Button><Button disabled={dirty || !title.trim()} loading={busy} onClick={() => action('publish')}>Publish quiz</Button></>}
        {quiz.status === 'published' && <Button variant="danger" loading={busy} onClick={() => action('close')}>Close quiz</Button>}
        <Button variant="secondary" onClick={() => setShowAnalytics(value => !value)}>{showAnalytics ? 'Review questions' : 'View analytics'}</Button>
        <Button variant="ghost" onClick={() => download('assessment.json', JSON.stringify({ title, questions }, null, 2), 'application/json')}>Export questions</Button>
      </div>
      {error && <Alert className="mt-4">{error}</Alert>}{notice && <Alert tone="success" className="mt-4">{notice}</Alert>}
      {editable && <p className="text-xs text-text-3 mt-3">Review every answer and cognitive label before publishing. Saving edits runs source and answer checks again. Published questions are locked for fair scoring.</p>}
    </Card>
    {showAnalytics ? <AssessmentAnalytics id={id} /> : questions.map((question, index) => <Card key={index}>
      <CardHeader title={`Question ${index + 1}`} hint={`${question.question_type} · ${question.bloom_level} · Difficulty ${question.difficulty}/5`} />
      {editable ? <Field id={`question-${index}`} label="Question"><FormInput id={`question-${index}`} placeholder="Question" value={question.question} onChange={value => change(index, { question: value })} multiline /></Field> : <h3 className="font-semibold text-lg">{question.question}</h3>}
      <div className="flex flex-col gap-2 mt-4">{question.options.map((option, optionIndex) => {
        const answers = Array.isArray(question.correct_answer) ? question.correct_answer : [question.correct_answer]
        const correct = answers.includes(option)
        return <div key={optionIndex} className={`flex gap-3 items-center border rounded-md p-3 ${correct ? 'border-success-line bg-success-soft' : 'border-border-strong'}`}>
          {editable && <input aria-label={`Mark option ${optionIndex + 1} correct for question ${index + 1}`} type={question.question_type === 'multiple' ? 'checkbox' : 'radio'} name={`answer-${index}`} checked={correct} onChange={() => change(index, { correct_answer: question.question_type === 'multiple' ? correct ? answers.filter(a => a !== option) : [...answers, option] : option })} className="accent-accent" />}
          {editable ? <input aria-label={`Question ${index + 1}, option ${optionIndex + 1}`} value={option} className="flex-1 min-w-0 bg-transparent text-base" onChange={e => {
            const value = e.target.value
            change(index, { options: question.options.map((o, i) => i === optionIndex ? value : o), correct_answer: Array.isArray(question.correct_answer) ? question.correct_answer.map(a => a === option ? value : a) : question.correct_answer === option ? value : question.correct_answer })
          }} /> : <span className="text-base break-words">{option}{correct ? ' ✓' : ''}</span>}
        </div>
      })}</div>
      <div className="mt-4">{editable ? <Field id={`explanation-${index}`} label="Explanation"><FormInput id={`explanation-${index}`} placeholder="Explain the answer" value={question.explanation} multiline onChange={value => change(index, { explanation: value })} /></Field> : <p className="text-sm text-text-2">{question.explanation}</p>}</div>
      {editable && <div className="grid sm:grid-cols-3 gap-3 mt-4">
        <Field id={`topic-${index}`} label="Topic"><FormInput id={`topic-${index}`} placeholder="Topic" value={question.topic} onChange={value => change(index, { topic: value })} /></Field>
        <Field id={`bloom-${index}`} label="Bloom level"><select id={`bloom-${index}`} value={question.bloom_level} onChange={e => change(index, { bloom_level: e.target.value as BloomLevel })} className="bg-surface border border-border-strong rounded-md p-2 text-base">{BLOOM_LEVELS.map(level => <option key={level}>{level}</option>)}</select></Field>
        <Field id={`difficulty-${index}`} label="Estimated difficulty"><select id={`difficulty-${index}`} value={question.difficulty} onChange={e => change(index, { difficulty: Number(e.target.value) })} className="bg-surface border border-border-strong rounded-md p-2 text-base">{[1, 2, 3, 4, 5].map(level => <option key={level} value={level}>{level}/5</option>)}</select></Field>
      </div>}
      <p className="text-xs text-text-3 mt-3">{question.bloom_rationale}</p>
      <div className="flex flex-col gap-3 mt-4">{question.evidence.map((source, i) => <SourceQuote key={i} source={source} />)}</div>
      {editable && questions.length > 1 && <Button variant="ghost" size="sm" className="mt-4" onClick={() => { setQuestions(previous => previous.filter((_, i) => i !== index)); setDirty(true) }}>Remove question</Button>}
    </Card>)}
  </div>
}

function AssessmentAnalytics({ id }: { id: string }) {
  const [data, setData] = useState<Analytics | null>(null)
  const [error, setError] = useState('')
  useEffect(() => { apiRequest<Analytics>(`/assessments/${id}/analytics`).then(setData).catch(e => setError(errorMessage(e))) }, [id])
  if (!data) return error ? <Alert>{error}</Alert> : <p role="status">Loading results…</p>
  const exportResults = () => {
    const cell = (value: unknown) => {
      const text = String(value ?? '')
      const safe = /^[=+@-]/.test(text) ? `'${text}` : text
      return `"${safe.replace(/"/g, '""')}"`
    }
    const rows = [['Name', 'Email', 'Status', 'Score', 'Total', 'Submitted at'], ...data.students.map(s => [s.name, s.email, s.status, s.score, s.total, s.submitted_at])]
    download('results.csv', rows.map(row => row.map(cell).join(',')).join('\r\n'), 'text/csv')
  }
  return <div className="flex flex-col gap-5">
    <div className="grid sm:grid-cols-3 gap-4">{[['Started', data.started], ['Completed', data.completed], ['Average score', data.average_percent === null ? 'No scores yet' : `${data.average_percent}%`]].map(([label, value]) => <Card key={label}><p className="text-sm text-text-3">{label}</p><p className="text-xl font-bold mt-2 tabular">{value}</p></Card>)}</div>
    <Card><CardHeader title="Topic performance" /><AccuracyTable values={data.topics} label="Topic" /></Card>
    <Card><CardHeader title="Cognitive level performance" /><AccuracyTable values={data.bloom_levels} label="Bloom level" /></Card>
    <Card><CardHeader title="Students" aside={<Button size="sm" variant="secondary" onClick={exportResults}>Export CSV</Button>} />
      <div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr><th className="py-2">Student</th><th>Status</th><th>Score</th></tr></thead>
        <tbody>{data.students.map(s => <tr key={s.attempt_id} className="border-t border-border-subtle"><td className="py-3 pr-3">{s.name}<span className="block text-xs text-text-3">{s.email}</span></td><td className="capitalize pr-3">{s.status}</td><td className="tabular">{s.score === null ? 'In progress' : `${s.score}/${s.total}`}</td></tr>)}</tbody>
      </table>{!data.students.length && <p className="text-sm text-text-3 py-3">No students have started this quiz.</p>}</div>
    </Card>
  </div>
}
