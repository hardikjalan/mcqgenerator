// Upload rules and helpers — shared by any role that picks files.
// Types live in @/types/upload

export const ALLOWED_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.png', '.jpg', '.jpeg']

// Per-file limit (capped at the cumulative ceiling so a single file can never
// silently violate the batch limit). Must stay ≤ MAX_CUMULATIVE_SIZE.
const MAX_FILE_SIZE = 5 * 1024 * 1024  // 5 MB

// Cumulative limit across ALL files in a single generate request.
// Must match MAX_CUMULATIVE_SIZE_MB in backend/main.py.
export const MAX_CUMULATIVE_SIZE = 5 * 1024 * 1024  // 5 MB

const ALLOWED_MIME_TYPES = [
  'application/pdf',
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'image/png',
  'image/jpeg',
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
  if (file.size > MAX_FILE_SIZE) return `Exceeds 5 MB per-file limit (${formatBytes(file.size)})`
  const ok =
    ALLOWED_MIME_TYPES.includes(file.type) ||
    ALLOWED_EXTENSIONS.some(ext => file.name.toLowerCase().endsWith(ext))
  if (!ok) return 'Unsupported type — use PDF, DOCX, PPTX, PNG or JPG'
  return null
}
