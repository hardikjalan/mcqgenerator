'use client'

import { useState, useCallback } from 'react'
import {
  Wand2, FilePlus2, BarChart3, CheckCircle2, AlertCircle,
} from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { apiRequest } from '@/lib/api'
import type { UploadedFile } from '@/types/upload'
import type { GeneratedQuestion, QuestionType, QuizConfig } from '@/types/quiz'
import { QUESTION_COUNTS, QUESTION_TYPES, BLOOM_LEVELS } from '@/lib/quiz-config'
import { validateFile, getFileExt, MAX_CUMULATIVE_SIZE } from '@/lib/file-upload'
import { AppShell, type NavItem } from '@/components/shared/AppShell'
import { useUser } from '@/components/shared/UserProvider'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'
import { Field, FormInput } from '@/components/ui/form-fields'
import { FileUploadZone } from '@/components/faculty/FileUploadZone'
import { ResultsView } from '@/components/faculty/ResultsView'
import { AssessmentWorkspace } from '@/components/shared/AssessmentWorkspace'

/** Mirrors SourceResult in backend/app/schemas.py — change both together. */
type ExtractedSource = { name: string; ok: boolean; chars: number; error: string | null }

export default function FacultyDashboard() {
  const [activeTab, setActiveTab] = useState<'create' | 'results' | 'library'>('create')
  const [assessmentId, setAssessmentId] = useState<string | null>(null)
  const nav: NavItem[] = [
    { label: 'Create', Icon: FilePlus2, active: activeTab === 'create', onClick: () => setActiveTab('create') },
    { label: 'Assessments', Icon: BarChart3, active: activeTab === 'library', onClick: () => setActiveTab('library') },
    { label: 'Latest draft', Icon: CheckCircle2, active: activeTab === 'results', onClick: () => setActiveTab('results') },
  ]
  return <AppShell nav={nav} roleLabel="Teacher" title={activeTab === 'create' ? 'Create a quiz' : activeTab === 'library' ? 'Your assessments' : 'Review assessment'}>
    <div hidden={activeTab !== 'create'}><QuizBuilder onQuestionsGenerated={(_questions, _config, id) => { setAssessmentId(id); setActiveTab('results') }} /></div>
    {activeTab === 'results' && <ResultsView assessmentId={assessmentId} onBackToCreate={() => setActiveTab('create')} />}
    {activeTab === 'library' && <AssessmentWorkspace />}
  </AppShell>
}

/** Lives inside AppShell so it can read the user the shell already fetched. */
function QuizBuilder({
  onQuestionsGenerated,
}: {
  onQuestionsGenerated: (questions: GeneratedQuestion[], config: QuizConfig, id: string) => void
}) {
  const { user } = useUser()
  const userId = user?.id ?? null

  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [sourceType, setSourceType] = useState<'upload' | 'text'>('upload')
  const [textContent, setTextContent] = useState('')

  const [config, setConfig] = useState<QuizConfig>({
    subjectName: '',
    topicsCovered: '',
    learningObjective: '',
    gradeLevel: '',
    questionType: 'single',
    questionCount: 10,
    customCount: '',
    timeLimit: '',
    bloomLevels: [...BLOOM_LEVELS],
    adaptive: true,
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
    try {
      const { error } = await supabase.storage.from('faculty-documents').upload(path, entry.file)
      if (error) throw new Error(error.message)
      setUploadedFiles(prev => prev.map(f => f.id === entry.id ? { ...f, status: 'done', progress: 100, storagePath: path } : f))
    } catch (error) {
      setUploadedFiles(prev => prev.map(f => f.id === entry.id ? { ...f, status: 'error', progress: 0, errorMsg: error instanceof Error ? error.message : 'Upload failed. Try again.' } : f))
    }
  }, [userId])

  const processFiles = useCallback((raw: FileList | File[]) => {
    if (!userId) { setGenError('Your account is still loading. Try the upload again.'); return }
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
        runningTotal -= file.size
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
  }, [uploadToStorage, uploadedFiles, userId])

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
      const { error } = await createClient().storage.from('faculty-documents').remove([entry.storagePath])
      if (error) { setGenError(error.message); return }
    }
    setUploadedFiles(prev => prev.filter(f => f.id !== entry.id))
  }

  // ── Readiness ──────────────────────────────────────────────────────────────
  const readyFiles = uploadedFiles.filter(f => f.status === 'done' && f.storagePath)

  // Says the single next thing to do, rather than listing everything missing.
  const missing =
    sourceType === 'upload' && uploadedFiles.some(f => f.status === 'uploading') ? 'Wait for the uploads to finish'
    : sourceType === 'upload' && readyFiles.length === 0 ? 'Add at least one file'
    : sourceType === 'text' && textContent.trim().length < 30 ? 'Paste at least 30 characters of material'
    : !config.subjectName.trim() ? 'Enter the subject'
    : !config.gradeLevel.trim() ? 'Say who it’s for'
    : !config.topicsCovered.trim() ? 'List the topics'
    : !config.learningObjective.trim() ? 'Describe what it should test'
    : config.questionCount < 1 || config.questionCount > 30 ? 'Choose between 1 and 30 questions'
    : Number(config.timeLimit) > 1440 ? 'Use a time limit of at most 1,440 minutes'
    : !config.bloomLevels?.length ? 'Select at least one cognitive level'
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
      const filesToUse = sourceType === 'upload' ? readyFiles : []
      const signed = await Promise.all(
        filesToUse.map(f =>
          supabase.storage.from('faculty-documents').createSignedUrl(f.storagePath!, 300)
        )
      )
      if (signed.some(item => item.error)) throw new Error('Could not prepare all document links. Retry the upload.')
      const filesPayload = filesToUse
        .map((f, i) => ({
          name: f.file.name,
          signedUrl: signed[i].data?.signedUrl ?? '',
          size_bytes: f.file.size,
        }))
        .filter(f => f.signedUrl)

      const data = await apiRequest<{ sources: ExtractedSource[]; questions: GeneratedQuestion[]; assessmentId: string }>('/generate-assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          sourceType,
          textContent: sourceType === 'text' ? textContent : null,
          files: filesPayload.length > 0 ? filesPayload : null,
          config: {
            subjectName: config.subjectName,
            topicsCovered: config.topicsCovered,
            learningObjective: config.learningObjective,
            gradeLevel: config.gradeLevel,
            questionType: config.questionType,
            questionCount: config.questionCount,
            timeLimit: config.timeLimit,
            bloomLevels: config.bloomLevels,
            adaptive: config.adaptive,
          },
        }),
      })

      setExtractedSources(data.sources ?? [])
      if (data.questions && Array.isArray(data.questions) && data.questions.length > 0) {
        onQuestionsGenerated(data.questions, config, data.assessmentId)
      }
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
          <div className="flex gap-2 mb-4"><Button size="sm" variant={sourceType === 'upload' ? 'primary' : 'secondary'} onClick={() => setSourceType('upload')}>Upload files</Button><Button size="sm" variant={sourceType === 'text' ? 'primary' : 'secondary'} onClick={() => setSourceType('text')}>Paste text</Button></div>
          {sourceType === 'text' ? <Field id="source-text" label="Course material" hint="Up to 100,000 characters."><FormInput id="source-text" multiline rows={10} placeholder="Paste your course material here" value={textContent} onChange={setTextContent} /></Field> : <FileUploadZone
            uploadedFiles={uploadedFiles}
            isDragging={isDragging}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onFileInput={handleFileInput}
            onRemove={removeFile}
          />}
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
            <fieldset><legend className="text-sm font-semibold text-text-2 mb-2">Cognitive levels</legend><div className="flex flex-wrap gap-3">{BLOOM_LEVELS.map(level => <label key={level} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.bloomLevels?.includes(level) ?? false} className="accent-accent" onChange={e => setConf({ bloomLevels: e.target.checked ? [...(config.bloomLevels ?? []), level] : config.bloomLevels?.filter(value => value !== level) })} />{level}</label>)}</div><p className="text-xs text-text-3 mt-2">Create-level MCQs assess proposed designs; they do not directly measure producing an original artefact.</p></fieldset>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={config.adaptive ?? true} onChange={e => setConf({ adaptive: e.target.checked })} className="accent-accent" />Adapt question order to student performance</label>

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
                    max={30}
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
