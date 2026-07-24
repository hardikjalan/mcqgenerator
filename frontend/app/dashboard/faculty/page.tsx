'use client'

import { useEffect, useState, useCallback } from 'react'
import { Layers, Wand2, LogOut } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import type { UploadedFile, ContentTab } from '@/types/upload'
import type { QuestionType, QuizConfig } from '@/types/quiz'
import { QUESTION_COUNTS, QUESTION_TYPES } from '@/lib/quiz-config'
import { validateFile, getFileExt, MAX_CUMULATIVE_SIZE } from '@/lib/file-upload'
import { SectionLabel, FormInput } from '@/components/ui/form-fields'
import { FileUploadZone } from '@/components/faculty/FileUploadZone'

// ── Logo (kept here as it's brand-specific, not reusable) ────────────────────
const CogniraLogo = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" className="text-indigo-400">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

// ── Component ─────────────────────────────────────────────────────────────────
export default function FacultyDashboard() {
  const [user, setUser] = useState<{ name: string; email: string; avatar: string; id: string } | null>(null)

  // Content source
  const [activeTab, setActiveTab] = useState<ContentTab>('upload')
  const [uploadedFiles, setUploadedFiles] = useState<UploadedFile[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const [textContent, setTextContent] = useState('')

  // Config
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

  // Generation
  const [isGenerating, setIsGenerating] = useState(false)
  const [genError, setGenError] = useState<string | null>(null)

  type ExtractedSource = { name: string; status: string; text: string; error: string | null }
  const [extractedSources, setExtractedSources] = useState<ExtractedSource[]>([])

  // Fetch user on mount
  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(({ data }) => {
      if (data.user) {
        setUser({
          id: data.user.id,
          name: data.user.user_metadata?.full_name ?? 'Faculty',
          email: data.user.email ?? '',
          avatar: data.user.user_metadata?.avatar_url ?? '',
        })
      }
    })
  }, [])

  const handleSignOut = async () => {
    const supabase = createClient()
    await supabase.auth.signOut()
    window.location.href = '/'
  }

  // ── File upload ────────────────────────────────────────────────────────────
  const uploadToStorage = useCallback(async (entry: UploadedFile) => {
    if (!user) return
    const supabase = createClient()
    const ext = getFileExt(entry.file.name)
    const path = `${user.id}/${Date.now()}_${Math.random().toString(36).slice(2)}.${ext}`

    // Animate progress while uploading
    const tick = setInterval(() => {
      setUploadedFiles(prev =>
        prev.map(f =>
          f.id === entry.id && f.status === 'uploading'
            ? { ...f, progress: Math.min(f.progress + 14, 85) }
            : f
        )
      )
    }, 180)

    const { error } = await supabase.storage.from('faculty-documents').upload(path, entry.file)
    clearInterval(tick)

    setUploadedFiles(prev =>
      prev.map(f =>
        f.id === entry.id
          ? error
            ? { ...f, status: 'error', progress: 0, errorMsg: error.message }
            : { ...f, status: 'done', progress: 100, storagePath: path }
          : f
      )
    )
  }, [user])

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
          errorMsg: `Batch limit reached — total ${totalMB} MB exceeds ${limitMB} MB cap`,
        }
      }

      return {
        id: `${Date.now()}_${Math.random()}`,
        file,
        status: 'uploading' as const,
        progress: 0,
      }
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
      const supabase = createClient()
      await supabase.storage.from('faculty-documents').remove([entry.storagePath])
    }
    setUploadedFiles(prev => prev.filter(f => f.id !== entry.id))
  }

  // ── Readiness check ────────────────────────────────────────────────────────
  const hasContent = activeTab === 'upload'
    ? uploadedFiles.some(f => f.status === 'done')
    : textContent.trim().split(/\s+/).filter(Boolean).length >= 50

  const isReady =
    hasContent &&
    config.subjectName.trim().length > 0 &&
    config.gradeLevel.trim().length > 0 &&
    config.topicsCovered.trim().length > 0 &&
    config.learningObjective.trim().length > 0

  // ── Generate — calls FastAPI backend ─────────────────────────────────────
  const handleGenerate = async () => {
    if (!isReady || isGenerating) return
    setGenError(null)
    setExtractedSources([])
    setIsGenerating(true)

    try {
      let filesPayload: { name: string; signedUrl: string }[] = []

      // Generate signed URLs for all successfully uploaded files
      if (activeTab === 'upload') {
        const supabase = createClient()
        const doneFiles = uploadedFiles.filter(f => f.status === 'done' && f.storagePath)
        const signed = await Promise.all(
          doneFiles.map(f =>
            supabase.storage.from('faculty-documents').createSignedUrl(f.storagePath!, 300)
          )
        )
        filesPayload = doneFiles.map((f, i) => ({
          name: f.file.name,
          signedUrl: signed[i].data?.signedUrl ?? '',
          size_bytes: f.file.size,
        })).filter(f => f.signedUrl)
      }

      const body = {
        sourceType: activeTab,
        textContent: activeTab === 'text' ? textContent : null,
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
      }

      const res = await fetch('http://localhost:8000/generate-assessment', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail ?? `Server error: ${res.status}`)
      }

      const data = await res.json()
      // Backend wraps success payload under "data" key via success_response()
      setExtractedSources(data.data?.extracted_sources ?? [])
    } catch (err: unknown) {
      setGenError(err instanceof Error ? err.message : 'Something went wrong. Is the backend running?')
    } finally {
      setIsGenerating(false)
    }
  }

  const setConf = (patch: Partial<QuizConfig>) => setConfig(p => ({ ...p, ...patch }))
  const wordCount = textContent.trim().split(/\s+/).filter(Boolean).length

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#030712] text-white font-sans selection:bg-indigo-500/30">

      {/* Background orbs */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
        <div className="absolute -top-32 -left-32 w-[560px] h-[560px] rounded-full bg-indigo-600/7 blur-[140px]" />
        <div className="absolute -bottom-32 -right-32 w-[500px] h-[500px] rounded-full bg-cyan-500/5 blur-[120px]" />
        <div
          className="absolute inset-0 opacity-[0.013]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.15) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.15) 1px,transparent 1px)',
            backgroundSize: '44px 44px',
          }}
        />
      </div>

      {/* Sticky top nav */}
      <header className="relative z-20 border-b border-white/[0.05] bg-[#030712]/80 backdrop-blur-xl sticky top-0">
        <div className="max-w-5xl mx-auto px-5 sm:px-8 py-3.5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-1.5 rounded-xl bg-slate-900 border border-slate-800">
              <CogniraLogo />
            </div>
            <div>
              <span className="text-sm font-bold text-white font-display tracking-tight">Cognira</span>
              <span className="hidden sm:block text-[9px] text-slate-600 uppercase tracking-widest font-semibold">
                Faculty Dashboard
              </span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {user?.avatar && (
              <img src={user.avatar} alt={user.name} className="w-7 h-7 rounded-full ring-2 ring-indigo-500/25" />
            )}
            <div className="hidden sm:block text-right">
              <div className="text-xs font-semibold text-white">{user?.name ?? '...'}</div>
              <div className="text-[10px] text-slate-600">{user?.email}</div>
            </div>
            <button
              onClick={handleSignOut}
              className="flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-medium text-slate-500 hover:text-rose-400 border border-slate-800/80 hover:border-rose-500/25 rounded-lg transition-all cursor-pointer"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </div>
      </header>

      {/* Page body */}
      <main className="relative z-10 max-w-5xl mx-auto px-5 sm:px-8 py-10 space-y-8">

        {/* Page heading */}
        <div>
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 border border-indigo-500/20 text-indigo-300 mb-3">
            <Wand2 className="w-3.5 h-3.5" />
            <span>AI Assessment Generator</span>
          </div>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white font-display tracking-tight leading-tight">
            Create New Assessment
          </h1>
          <p className="text-sm text-slate-500 mt-1.5 max-w-lg">
            Provide your course material and configure your quiz — Cognira will do the rest.
          </p>
        </div>

        {/* ═══ STEP 1 — Content Source ══════════════════════════════════════ */}
        <section className="rounded-2xl border border-white/[0.06] bg-[#070d1a]/60 backdrop-blur-sm overflow-hidden">

          {/* Tab bar */}
          <div className="flex border-b border-white/[0.05]">
            {(['upload', 'text'] as ContentTab[]).map(tab => (
              <button
                key={tab}
                id={`tab-${tab}`}
                onClick={() => setActiveTab(tab)}
                className={`relative px-7 py-3.5 text-xs font-bold tracking-wide transition-all duration-200 cursor-pointer ${
                  activeTab === tab ? 'text-indigo-300' : 'text-slate-600 hover:text-slate-400'
                }`}
              >
                {tab === 'upload' ? '↑  Upload Files' : '≡  Paste Text'}
                {activeTab === tab && (
                  <span className="absolute bottom-0 left-4 right-4 h-[2px] rounded-full bg-gradient-to-r from-indigo-500 to-purple-500" />
                )}
              </button>
            ))}
          </div>

          {/* Upload tab */}
          {activeTab === 'upload' && (
            <div className="p-6">
              <FileUploadZone
                uploadedFiles={uploadedFiles}
                isDragging={isDragging}
                onDrop={handleDrop}
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onFileInput={handleFileInput}
                onRemove={removeFile}
              />
            </div>
          )}

          {/* Text tab */}
          {activeTab === 'text' && (
            <div className="p-6 space-y-3">
              <textarea
                id="text-content-input"
                value={textContent}
                onChange={e => setTextContent(e.target.value)}
                placeholder="Paste your lecture notes, textbook content, syllabus, or any material you want to generate MCQs from…"
                rows={14}
                className="w-full bg-[#0a0f1e] border border-slate-800 rounded-xl px-5 py-4 text-sm text-slate-100 placeholder:text-slate-700 resize-none focus:outline-none focus:border-indigo-500/60 transition-all duration-200 leading-relaxed"
              />
              <div className="flex justify-between px-1">
                <span className={`text-[11px] font-medium ${wordCount < 50 ? 'text-amber-500' : 'text-emerald-400'}`}>
                  {wordCount} words {wordCount < 50 ? `· needs ${50 - wordCount} more` : '· content ready'}
                </span>
                <button
                  onClick={() => setTextContent('')}
                  disabled={!textContent}
                  className="text-[11px] text-slate-600 hover:text-rose-400 disabled:opacity-30 transition-colors cursor-pointer"
                >
                  Clear
                </button>
              </div>
            </div>
          )}
        </section>

        {/* ═══ STEP 2 — Assessment Configuration ══════════════════════════════ */}
        <section className="rounded-2xl border border-white/[0.06] bg-[#070d1a]/60 backdrop-blur-sm p-6 sm:p-8 space-y-8">

          <div className="pb-2 border-b border-white/[0.05]">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-indigo-400" />
              <h2 className="text-base font-bold text-white font-display">Assessment Configuration</h2>
            </div>
            <p className="text-xs text-slate-600 mt-0.5 ml-6">Fill in all details to customise how your MCQs are generated</p>
          </div>

          {/* Row 1: Subject Name + Target Audience */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
            <div>
              <SectionLabel step={1}>Subject Name</SectionLabel>
              <FormInput
                id="subject-name-input"
                placeholder="e.g. Data Structures and Algorithms"
                value={config.subjectName}
                onChange={v => setConf({ subjectName: v })}
              />
            </div>
            <div>
              <SectionLabel step={2}>Target Audience</SectionLabel>
              <FormInput
                id="grade-level-input"
                placeholder="e.g. 2nd year B.Tech CSE students with basic programming knowledge"
                value={config.gradeLevel}
                onChange={v => setConf({ gradeLevel: v })}
              />
            </div>
          </div>

          {/* Topics to Focus On */}
          <div>
            <SectionLabel step={3}>Topics to Focus On</SectionLabel>
            <FormInput
              id="topics-input"
              placeholder="e.g. Binary Trees, Graph Traversal, Dynamic Programming — separate topics with commas"
              value={config.topicsCovered}
              onChange={v => setConf({ topicsCovered: v })}
              multiline
              rows={2}
            />
          </div>

          {/* Learning Objective */}
          <div>
            <SectionLabel step={4}>Learning Objective</SectionLabel>
            <FormInput
              id="learning-objective-input"
              placeholder="e.g. Test students' understanding of tree traversal algorithms and their time complexities after Chapter 5…"
              value={config.learningObjective}
              onChange={v => setConf({ learningObjective: v })}
              multiline
              rows={3}
            />
          </div>

          <div className="border-t border-white/[0.04]" />

          {/* Question Type */}
          <div>
            <SectionLabel step={5}>Question Type</SectionLabel>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {QUESTION_TYPES.map(qt => {
                const active = config.questionType === qt.key
                return (
                  <button
                    key={qt.key}
                    id={`qtype-${qt.key}`}
                    onClick={() => setConf({ questionType: qt.key as QuestionType })}
                    className={`group relative flex flex-col items-center justify-center gap-1.5 py-5 rounded-2xl border text-center transition-all duration-200 cursor-pointer ${
                      active
                        ? 'border-indigo-500/60 bg-indigo-500/10 shadow-[0_0_32px_rgba(99,102,241,0.12)]'
                        : 'border-slate-800/70 bg-[#0b0f1a] hover:border-slate-700 hover:bg-slate-800/30'
                    }`}
                  >
                    <span className={`text-2xl leading-none transition-transform duration-200 ${active ? 'scale-110' : 'group-hover:scale-105'}`}>{qt.icon}</span>
                    <span className={`text-xs font-bold ${active ? 'text-indigo-300' : 'text-slate-400'}`}>{qt.label}</span>
                    <span className={`text-[10px] ${active ? 'text-indigo-400/70' : 'text-slate-600'}`}>{qt.desc}</span>
                    {active && <span className="absolute top-2.5 right-2.5 w-1.5 h-1.5 rounded-full bg-indigo-400" />}
                  </button>
                )
              })}
            </div>
          </div>

          <div className="border-t border-white/[0.04]" />

          {/* Number of Questions + Time Limit */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">

            <div>
              <SectionLabel step={6}>Number of Questions</SectionLabel>
              <div className="flex gap-2 mb-3">
                {QUESTION_COUNTS.map(n => {
                  const active = config.questionCount === n && !config.customCount
                  return (
                    <button
                      key={n}
                      id={`qcount-${n}`}
                      onClick={() => setConf({ questionCount: n, customCount: '' })}
                      className={`flex-1 py-2.5 rounded-xl text-xs font-bold border transition-all duration-200 cursor-pointer ${
                        active
                          ? 'bg-indigo-500/15 border-indigo-500/50 text-indigo-300'
                          : 'border-slate-800 bg-[#0b0f1a] text-slate-500 hover:text-slate-300 hover:border-slate-700'
                      }`}
                    >
                      {n}
                    </button>
                  )
                })}
              </div>
              <div className="flex items-center gap-3">
                <span className="text-[11px] text-slate-600 whitespace-nowrap">Custom:</span>
                <input
                  id="qcount-custom"
                  type="number"
                  min={1}
                  max={100}
                  placeholder="e.g. 25"
                  value={config.customCount}
                  onChange={e => {
                    const v = e.target.value
                    setConf({ customCount: v, questionCount: v ? parseInt(v) || 10 : 10 })
                  }}
                  className="w-full bg-[#0b0f1a] border border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-200 placeholder:text-slate-700 focus:outline-none focus:border-indigo-500/60 transition-all"
                />
              </div>
            </div>

            <div>
              <SectionLabel step={7}>Quiz Time Limit</SectionLabel>
              <div className="flex items-center gap-3">
                <input
                  id="time-limit-input"
                  type="text"
                  inputMode="numeric"
                  placeholder="e.g. 30"
                  value={config.timeLimit}
                  onChange={e => setConf({ timeLimit: e.target.value.replace(/\D/g, '') })}
                  className="flex-1 bg-[#0b0f1a] border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/70 transition-all duration-200"
                />
                <span className="text-sm text-slate-500 font-medium whitespace-nowrap">minutes</span>
              </div>
            </div>

          </div>

          {/* Generate button */}
          <div className="pt-2 space-y-3">
            <button
              id="generate-assessment-btn"
              onClick={handleGenerate}
              disabled={!isReady || isGenerating}
              className={`w-full flex items-center justify-center gap-2.5 py-4 rounded-2xl font-bold text-sm transition-all duration-300 cursor-pointer ${
                isReady && !isGenerating
                  ? 'btn-primary-glow text-white'
                  : 'bg-slate-900/50 border border-slate-800/60 text-slate-700 cursor-not-allowed'
              }`}
            >
              {isGenerating ? (
                <>
                  <Wand2 className="w-4 h-4 animate-pulse" />
                  <span>Generating Assessment…</span>
                </>
              ) : (
                <>
                  <Wand2 className="w-4 h-4" />
                  <span>Generate Assessment</span>
                </>
              )}
            </button>

            {!isReady && !isGenerating && (
              <p className="text-center text-[11px] text-slate-700">
                {!hasContent
                  ? activeTab === 'upload'
                    ? 'Upload at least one file to continue'
                    : 'Paste at least 50 words to continue'
                  : !config.subjectName.trim()
                  ? 'Enter the Subject Name to continue'
                  : !config.gradeLevel.trim()
                  ? 'Describe the Target Audience to continue'
                  : !config.topicsCovered.trim()
                  ? 'Enter Topics to Focus On to continue'
                  : 'Fill in the Learning Objective to continue'}
              </p>
            )}

            {genError && (
              <div className="p-3.5 rounded-xl border border-amber-500/20 bg-amber-500/6 text-[11px] text-amber-300 flex items-start gap-2">
                <span className="flex-shrink-0">⚡</span>
                <span>{genError}</span>
              </div>
            )}
          </div>

        </section>
        {/* ═══ STEP 3 — Extracted Content Preview ══════════════════════════════ */}
        {extractedSources.length > 0 && (
          <section className="rounded-2xl border border-white/[0.06] bg-[#070d1a]/60 backdrop-blur-sm p-6 sm:p-8 space-y-5">
            <div className="pb-2 border-b border-white/[0.05]">
              <div className="flex items-center gap-2">
                <span className="text-indigo-400 text-base">✦</span>
                <h2 className="text-base font-bold text-white font-display">Extracted Content</h2>
                <span className="ml-auto text-[11px] text-emerald-400 font-semibold bg-emerald-500/10 border border-emerald-500/20 px-2 py-0.5 rounded-full">
                  {extractedSources.filter(s => s.status === 'success').length}/{extractedSources.length} extracted
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-0.5 ml-6">Text successfully pulled from your sources — ready for the next RAG step</p>
            </div>

            <div className="space-y-4">
              {extractedSources.map((src, i) => (
                <div key={i} className={`rounded-xl border p-4 space-y-2 ${
                  src.status === 'success'
                    ? 'border-emerald-500/20 bg-emerald-500/5'
                    : 'border-rose-500/20 bg-rose-500/5'
                }`}>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-bold ${
                      src.status === 'success' ? 'text-emerald-400' : 'text-rose-400'
                    }`}>
                      {src.status === 'success' ? '✓' : '✗'}
                    </span>
                    <span className="text-sm font-semibold text-slate-200 truncate">{src.name}</span>
                    {src.status === 'success' && (
                      <span className="ml-auto text-[10px] text-slate-500 whitespace-nowrap">
                        {src.text.length.toLocaleString()} chars
                      </span>
                    )}
                  </div>
                  {src.status === 'error' ? (
                    <p className="text-xs text-rose-400 pl-4">{src.error}</p>
                  ) : (
                    <pre className="text-[11px] text-slate-400 bg-black/30 rounded-lg p-3 max-h-40 overflow-y-auto whitespace-pre-wrap leading-relaxed">
                      {src.text.slice(0, 800)}{src.text.length > 800 ? '…' : ''}
                    </pre>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}

      </main>
    </div>
  )
}
