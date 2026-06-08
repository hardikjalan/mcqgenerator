// Shared types for the Faculty Dashboard feature

export type UploadedFile = {
  id: string
  file: File
  status: 'uploading' | 'done' | 'error'
  progress: number
  storagePath?: string
  errorMsg?: string
}

export type ContentTab = 'upload' | 'text'

export type QuestionType = 'single' | 'multiple' | 'truefalse' | 'all'

export type QuizConfig = {
  subjectName: string
  topicsCovered: string
  learningObjective: string
  gradeLevel: string
  questionType: QuestionType
  questionCount: number
  customCount: string
  timeLimit: string
}

export const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.png', '.jpg', '.jpeg']
export const MAX_FILE_SIZE = 10 * 1024 * 1024

export const ALLOWED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'image/png',
  'image/jpeg',
]

export const QUESTION_COUNTS = [5, 10, 15, 20]

export const QUESTION_TYPES: { key: QuestionType; label: string; desc: string; icon: string }[] = [
  { key: 'single',    label: 'Single Correct',   desc: 'One right answer',   icon: '◉' },
  { key: 'multiple',  label: 'Multiple Correct',  desc: 'Many right answers', icon: '☑' },
  { key: 'truefalse', label: 'True / False',      desc: 'Binary choice',      icon: '⇌' },
  { key: 'all',       label: 'All Types',         desc: 'Mix of all above',   icon: '⊞' },
]

// ── Helpers ────────────────────────────────────────────────────────────────────
export function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export function getFileExt(filename: string) {
  return filename.split('.').pop()?.toLowerCase() ?? ''
}

export function validateFile(file: File): string | null {
  if (file.size > MAX_FILE_SIZE) return `Exceeds 10 MB limit (${formatBytes(file.size)})`
  const ok =
    ALLOWED_MIME_TYPES.includes(file.type) ||
    ALLOWED_EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext))
  if (!ok) return 'Unsupported type — use PDF, DOCX, PPTX, PNG or JPG'
  return null
}
