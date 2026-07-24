/**
 * types/upload.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Types for the content-source / file-upload flow.
 *
 * Role-agnostic: faculty upload reference material here today, and the same
 * shapes are reused wherever a file picker appears (e.g. student submissions).
 *
 * Runtime rules (size caps, allowed types, validators) live in @/lib/file-upload
 */

export type UploadedFile = {
  id: string
  file: File
  status: 'uploading' | 'done' | 'error'
  progress: number
  storagePath?: string
  errorMsg?: string
}
