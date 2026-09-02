'use client'

import { useState, useCallback } from 'react'
import {
  Wand2, FilePlus2, Library, BarChart3, Users, FileCheck2, CheckCircle2, AlertCircle,
} from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { apiUrl } from '@/lib/env'
import type { UploadedFile } from '@/types/upload'
import type { QuestionType, QuizConfig } from '@/types/quiz'
import { QUESTION_COUNTS, QUESTION_TYPES } from '@/lib/quiz-config'
import { validateFile, getFileExt, MAX_CUMULATIVE_SIZE } from '@/lib/file-upload'
import { AppShell, type NavItem } from '@/components/shared/AppShell'
import { useUser } from '@/components/shared/UserProvider'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'
import { Field, FormInput } from '@/components/ui/form-fields'
import { FileUploadZone } from '@/components/faculty/FileUploadZone'

const NAV: NavItem[] = [
  { label: 'Create',        href: '/dashboard/faculty', Icon: FilePlus2 },
  { label: 'My quizzes',    Icon: Library },
  { label: 'Question bank', Icon: FileCheck2 },
  { label: 'Cohorts',       Icon: Users },
  { label: 'Results',       Icon: BarChart3 },
]

/** Mirrors SourceResult in backend/app/schemas.py — change both together. */
type ExtractedSource = { name: string; ok: boolean; chars: number; error: string | null }

export default function FacultyDashboard() {
  return (
    <AppShell nav={NAV} roleLabel="Teacher" title="Create a quiz">
      <QuizBuilder />
    </AppShell>
  )
}

/** Lives inside AppShell so it can read the user the shell already fetched. */
function QuizBuilder() {
  const { user } = useUser()
  const userId = user?.id ?? null

  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [isDragging, setIsDragging] = useState(false)

  const [config, setConfig] = useState<QuizConfig>({
    subjectName: '',
    topicsCovered: '',
    learningObjective: '',
    gradeLevel: '',
    questionType: 'single',
    questionCount: 10,
    customCount: '',
    timeLimit: '',
  })

  const [isGenerating, setIsGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)
  const [extractedSources, setExtractedSources] = useState<ExtractedSource[]>([])

  // ── Upload ─────────────────────────────────────────────────────────────────
  const uploadToStorage = useCallback(async (entry: UploadedFile) => {
    if (!userId) return
    const supabase = createClient()
    const ext = getFileExt(entry.file.name)
    const path = `${userId}/${Date.now()}_${Math.random().toString(36).slice(2)}.${ext}`

    // No progress ticker here on purpose. Supabase's upload doesn't report
    // bytes sent, so the old timer was inventing a percentage that had nothing
    // to do with the transfer — it read "85%" on a stalled upload. The row
    // shows an indeterminate bar instead, which is the truth.
    const { error } = await supabase.storage.from('faculty-documents').upload(path, entry.file)

    setUploadedFiles(prev =>
      prev.map(f =>
        f.id === entry.id
          ? error
            ? { ...f, status: 'error', progress: 0, errorMsg: error.message }
            : { ...f, status: 'done', progress: 100, storagePath: path }
          : f
      )
    )
  }, [userId])

  const processFiles = useCallback((raw: FileList | File[]) => {
    // Bytes already committed (uploading or done) — errors don't count
    const alreadyUsed = uploadedFiles
      .filter(f => f.status !== 'error')
      .reduce((sum, f) => sum + f.file.size, 0)

    let runningTotal = alreadyUsed
    const entries: UploadedFile[] = Array.from(raw).map(file => {
      // 1. Per-file validation (type + individual size limit)
      const perFileErr = validateFile(file)
      if (perFileErr) {
        return {
          id: `${Date.now()}_${Math.random()}`,
          file,
          status: 'error' as const,
          progress: 0,
          errorMsg: perFileErr,
        }
      }

      // 2. Cumulative size guard
      runningTotal += file.size
      if (runningTotal > MAX_CUMULATIVE_SIZE) {
        const limitMB = (MAX_CUMULATIVE_SIZE / (1024 * 1024)).toFixed(0)
        const totalMB = (runningTotal / (1024 * 1024)).toFixed(1)
        return {
          id: `${Date.now()}_${Math.random()}`,
          file,
          status: 'error' as const,
          progress: 0,
          errorMsg: `That takes you to ${totalMB} MB — the limit is ${limitMB} MB in total`,
        }
      }

      return { id: `${Date.now()}_${Math.random()}`, file, status: 'uploading' as const, progress: 0 }
    })

    setUploadedFiles(prev => [...prev, ...entries])
    entries.filter(e => e.status === 'uploading').forEach(e => uploadToStorage(e))
  }, [uploadToStorage, uploadedFiles])

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    if (e.dataTransfer.files?.length) processFiles(e.dataTransfer.files)
  }
  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true) }
  const handleDragLeave = () => setIsDragging(false)
  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.length) processFiles(e.target.files)
    e.target.value = ''
  }

  const removeFile = async (entry: UploadedFile) => {
    if (entry.storagePath) {
      await createClient().storage.from('faculty-documents').remove([entry.storagePath])
    }
    setUploadedFiles(prev => prev.filter(f => f.id !== entry.id))
  }

  // ── Readiness ──────────────────────────────────────────────────────────────
  const readyFiles = uploadedFiles.filter(f => f.status === 'done' && f.storagePath)

  // Says the single next thing to do, rather than listing everything missing.
  const missing =
    readyFiles.length === 0 ? 'Add at least one file'
    : !config.subjectName.trim() ? 'Enter the subject'
    : !config.gradeLevel.trim() ? 'Say who it’s for'
    : !config.topicsCovered.trim() ? 'List the topics'
    : !config.learningObjective.trim() ? 'Describe what it should test'
    : null

  const isReady = missing === null

  // ── Generate ───────────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!isReady || isGenerating) return
    setGenError(null)
    setExtractedSources([])
    setIsGenerating(true)

    try {
      const supabase = createClient()
      const signed = await Promise.all(
        readyFiles.map(f =>
          supabase.storage.from('faculty-documents').createSignedUrl(f.storagePath!, 300)
        )
      )
      const filesPayload = readyFiles
        .map((f, i) => ({
          name: f.file.name,
          signedUrl: signed[i].data?.signedUrl ?? '',
          size_bytes: f.file.size,
        }))
        .filter(f => f.signedUrl)

      const res = await fetch(apiUrl('/generate-assessment'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sourceType: 'upload',
          textContent: null,
          files: filesPayload.length > 0 ? filesPayload : null,
          config: {
            subjectName: config.subjectName,
            topicsCovered: config.topicsCovered,
            learningObjective: config.learningObjective,
            gradeLevel: config.gradeLevel,
            questionType: config.questionType,
            questionCount: config.questionCount,
            timeLimit: config.timeLimit,
          },
        }),
      })

      if (!res.ok) {
        // Every backend failure is {"error": "<one sentence>"} — safe to show.
        const err = await res.json().catch(() => ({}))
        throw new Error(err.error ?? `Server error: ${res.status}`)
      }

      const data = await res.json()
      setExtractedSources(data.sources ?? [])
    } catch (err: unknown) {
      setGenError(
        err instanceof Error ? err.message : 'Couldn’t reach the server. Is the backend running?'
      )
    } finally {
      setIsGenerating(false)
    }
  }

  const setConf = (patch: Partial<QuizConfig>) => setConfig(p => ({ ...p, ...patch }))

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="max-w-6xl mx-auto grid lg:grid-cols-[minmax(0,1fr)_336px] gap-5 items-start">

      {/* ── Left: the form ──────────────────────────────────────────── */}
      <div className="flex flex-col gap-5 min-w-0">

        <Card>
          <CardHeader
            title="Course material"
            hint="What the questions get written from."
            aside={<span className="text-xs text-text-3 tabular">{readyFiles.length} ready</span>}
          />
          <FileUploadZone
            uploadedFiles={uploadedFiles}
            isDragging={isDragging}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onFileInput={handleFileInput}
            onRemove={removeFile}
          />
        </Card>

        <Card>
          <CardHeader title="About the quiz" hint="All four are needed." />
          <div className="flex flex-col gap-4">
            <div className="grid sm:grid-cols-2 gap-4">
              <Field id="subject-name-input" label="Subject">
                <FormInput
                  id="subject-name-input"
                  placeholder="Data Structures and Algorithms"
                  value={config.subjectName}
                  onChange={v => setConf({ subjectName: v })}
                />
              </Field>
              <Field id="grade-level-input" label="Who is it for?">
                <FormInput
                  id="grade-level-input"
                  placeholder="2nd year B.Tech CSE"
                  value={config.gradeLevel}
                  onChange={v => setConf({ gradeLevel: v })}
                />
              </Field>
            </div>

            <Field id="topics-input" label="Topics to cover" hint="Separate them with commas.">
              <FormInput
                id="topics-input"
                placeholder="Binary trees, graph traversal, dynamic programming"
                value={config.topicsCovered}
                onChange={v => setConf({ topicsCovered: v })}
              />
            </Field>

            <Field id="learning-objective-input" label="What should it test?">
              <FormInput
                id="learning-objective-input"
                placeholder="Whether students understand tree traversal and can work out time complexity after Chapter 5"
                value={config.learningObjective}
                onChange={v => setConf({ learningObjective: v })}
                multiline
                rows={3}
              />
            </Field>
          </div>
        </Card>

        <Card>
          <CardHeader title="Questions" />
          <div className="flex flex-col gap-5">

            <div className="flex flex-col gap-2">
              <span className="text-sm font-semibold text-text-2">Type</span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {QUESTION_TYPES.map(qt => {
                  const active = config.questionType === qt.key
                  return (
                    <button
                      key={qt.key}
                      id={`qtype-${qt.key}`}
                      onClick={() => setConf({ questionType: qt.key as QuestionType })}
                      aria-pressed={active}
                      className={[
                        'flex flex-col items-start gap-0.5 px-3 py-2.5 rounded-md border text-left transition-colors cursor-pointer',
                        active
                          ? 'border-accent bg-accent-soft'
                          : 'border-border-strong bg-surface hover:border-text-3 hover:bg-surface-2',
                      ].join(' ')}
                    >
                      <span className={`text-base font-semibold ${active ? 'text-accent' : 'text-text'}`}>
                        {qt.label}
                      </span>
                      <span className="text-xs text-text-3">{qt.desc}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            <div className="grid sm:grid-cols-2 gap-5">
              <div className="flex flex-col gap-2">
                <span className="text-sm font-semibold text-text-2">How many</span>
                <div className="flex gap-2">
                  {QUESTION_COUNTS.map(n => {
                    const active = config.questionCount === n && !config.customCount
                    return (
                      <button
                        key={n}
                        id={`qcount-${n}`}
                        onClick={() => setConf({ questionCount: n, customCount: '' })}
                        aria-pressed={active}
                        className={[
                          'flex-1 py-2 rounded-md border text-base font-semibold tabular transition-colors cursor-pointer',
                          active
                            ? 'border-accent bg-accent-soft text-accent'
                            : 'border-border-strong bg-surface text-text-2 hover:border-text-3 hover:bg-surface-2',
                        ].join(' ')}
                      >
                        {n}
                      </button>
                    )
                  })}
                  <input
                    id="qcount-custom"
                    type="number"
                    min={1}
                    max={100}
                    placeholder="Other"
                    aria-label="Custom number of questions"
                    value={config.customCount}
                    onChange={e => {
                      const v = e.target.value
                      setConf({ customCount: v, questionCount: v ? parseInt(v) || 10 : 10 })
                    }}
                    className="w-20 bg-surface border border-border-strong rounded-md px-2.5 py-2 text-base text-text placeholder:text-text-3 tabular hover:border-text-3 focus:border-accent focus:outline-none transition-colors"
                  />
                </div>
              </div>

              <Field id="time-limit-input" label="Time limit" hint="Minutes. Leave empty for no limit.">
                <input
                  id="time-limit-input"
                  type="text"
                  inputMode="numeric"
                  placeholder="30"
                  value={config.timeLimit}
                  onChange={e => setConf({ timeLimit: e.target.value.replace(/\D/g, '') })}
                  className="w-full bg-surface border border-border-strong rounded-md px-3.5 py-2.5 text-base text-text placeholder:text-text-3 tabular hover:border-text-3 focus:border-accent focus:outline-none transition-colors"
                />
              </Field>
            </div>
          </div>
        </Card>
      </div>

      {/* ── Right: summary and the action ───────────────────────────── */}
      <div className="flex flex-col gap-4 lg:sticky lg:top-20">
        <Card>
          <CardHeader title="Summary" />
          <dl className="flex flex-col gap-2.5 text-base">
            {[
              ['Subject', config.subjectName || '—'],
              ['For', config.gradeLevel || '—'],
              ['Type', QUESTION_TYPES.find(q => q.key === config.questionType)?.label ?? '—'],
              ['Questions', String(config.questionCount)],
              ['Time', config.timeLimit ? `${config.timeLimit} min` : 'No limit'],
              ['Files', String(readyFiles.length)],
            ].map(([label, value]) => (
              <div key={label} className="flex items-baseline justify-between gap-3">
                <dt className="text-text-3 shrink-0">{label}</dt>
                <dd className="text-text font-medium text-right truncate">{value}</dd>
              </div>
            ))}
          </dl>

          <div className="mt-5 flex flex-col gap-2.5">
            <Button
              id="generate-assessment-btn"
              block
              size="lg"
              disabled={!isReady}
              loading={isGenerating}
              onClick={handleGenerate}
            >
              {!isGenerating && <Wand2 className="w-4 h-4" aria-hidden="true" />}
              {isGenerating ? 'Working…' : 'Generate questions'}
            </Button>

            {missing && !isGenerating && (
              <p className="text-xs text-text-3 text-center">{missing}</p>
            )}
          </div>

          {genError && <Alert tone="error" className="mt-3">{genError}</Alert>}
        </Card>

        {extractedSources.length > 0 && (
          <Card>
            <CardHeader
              title="Read from your files"
              aside={
                <span className="text-xs text-text-3 tabular">
                  {extractedSources.filter(s => s.ok).length}/{extractedSources.length}
                </span>
              }
            />
            <ul className="flex flex-col gap-2.5">
              {extractedSources.map((src, i) => (
                <li key={i} className="flex flex-col gap-1">
                  <span className="flex items-center gap-2 min-w-0">
                    {src.ok
                      ? <CheckCircle2 className="w-3.5 h-3.5 text-success shrink-0" aria-hidden="true" />
                      : <AlertCircle className="w-3.5 h-3.5 text-danger shrink-0" aria-hidden="true" />}
                    <span className="text-sm text-text truncate flex-1">{src.name}</span>
                    {src.ok && (
                      <span className="text-xs text-text-3 tabular shrink-0">
                        {src.chars.toLocaleString()} ch
                      </span>
                    )}
                  </span>
                  {!src.ok && src.error && (
                    <p className="text-xs text-danger pl-6">{src.error}</p>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  )
}
