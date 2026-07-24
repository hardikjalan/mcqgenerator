'use client'

import { useRef } from 'react'
import { CloudUpload, X, CheckCircle2, AlertCircle, FileText, FileImage, FileSpreadsheet } from 'lucide-react'
import type { UploadedFile } from '@/types/upload'
import { ALLOWED_EXTENSIONS, formatBytes, getFileExt } from '@/lib/file-upload'
import { Spinner } from '@/components/ui/Spinner'

function FileTypeIcon({ ext }: { ext: string }) {
  if (ext === 'pdf') return <FileText className="w-4 h-4 text-danger shrink-0" />
  if (ext === 'docx') return <FileText className="w-4 h-4 text-accent shrink-0" />
  if (ext === 'pptx') return <FileSpreadsheet className="w-4 h-4 text-warning shrink-0" />
  return <FileImage className="w-4 h-4 text-success shrink-0" />
}

// ── Single file row ───────────────────────────────────────────────────────────
function FileListItem({ entry, onRemove }: { entry: UploadedFile; onRemove: (e: UploadedFile) => void }) {
  return (
    <li
      className={[
        'flex items-center gap-3 px-3 py-2.5 rounded-md border transition-colors',
        entry.status === 'error'
          ? 'border-danger-line bg-danger-soft'
          : 'border-border-subtle bg-surface',
      ].join(' ')}
    >
      <FileTypeIcon ext={getFileExt(entry.file.name)} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-3">
          <span className="text-base text-text truncate">{entry.file.name}</span>
          <span className="text-xs text-text-3 tabular shrink-0">{formatBytes(entry.file.size)}</span>
        </div>

        {entry.status === 'uploading' && (
          // Indeterminate: the upload doesn't report bytes sent, so this shows
          // that something is happening without claiming to know how far along.
          <div
            className="mt-1.5 h-1 rounded-full bg-surface-2 overflow-hidden"
            role="progressbar"
            aria-label={`Uploading ${entry.file.name}`}
          >
            <div className="h-full w-2/5 rounded-full bg-accent animate-slide" />
          </div>
        )}

        {entry.status === 'error' && entry.errorMsg && (
          <p className="mt-0.5 text-xs text-danger">{entry.errorMsg}</p>
        )}
      </div>

      <span className="shrink-0 flex items-center gap-1">
        {entry.status === 'uploading' && <Spinner size={14} className="text-text-3" />}
        {entry.status === 'done' && <CheckCircle2 className="w-4 h-4 text-success" aria-label="Uploaded" />}
        {entry.status === 'error' && <AlertCircle className="w-4 h-4 text-danger" aria-label="Failed" />}
        <button
          onClick={() => onRemove(entry)}
          aria-label={`Remove ${entry.file.name}`}
          className="p-1 rounded-sm text-text-3 hover:text-danger hover:bg-surface-2 cursor-pointer transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </span>
    </li>
  )
}

// ── Drop zone ─────────────────────────────────────────────────────────────────
type FileUploadZoneProps = {
  uploadedFiles: UploadedFile[]
  isDragging: boolean
  onDrop: (e: React.DragEvent) => void
  onDragOver: (e: React.DragEvent) => void
  onDragLeave: () => void
  onFileInput: (e: React.ChangeEvent<HTMLInputElement>) => void
  onRemove: (entry: UploadedFile) => void
}

export function FileUploadZone({
  uploadedFiles,
  isDragging,
  onDrop,
  onDragOver,
  onDragLeave,
  onFileInput,
  onRemove,
}: FileUploadZoneProps) {
  const fileInputRef = useRef<HTMLInputElement>(null)

  return (
    <div className="flex flex-col gap-3">
      <button
        type="button"
        id="file-drop-zone"
        onClick={() => fileInputRef.current?.click()}
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        className={[
          'w-full flex flex-col items-center justify-center gap-1.5 py-9 px-4',
          'rounded-lg border border-dashed cursor-pointer transition-colors text-center',
          isDragging
            ? 'border-accent bg-accent-soft'
            : 'border-border-strong bg-surface-2 hover:border-accent hover:bg-accent-soft',
        ].join(' ')}
      >
        <CloudUpload
          className={`w-6 h-6 mb-0.5 ${isDragging ? 'text-accent' : 'text-text-3'}`}
          aria-hidden="true"
        />
        <span className="text-base font-semibold text-text">
          {isDragging ? 'Drop them here' : 'Drop files here, or click to browse'}
        </span>
        <span className="text-xs text-text-3">
          PDF · DOCX · PPTX · PNG · JPG — 5 MB in total
        </span>
      </button>

      <input
        ref={fileInputRef}
        type="file"
        multiple
        accept={ALLOWED_EXTENSIONS.join(',')}
        className="hidden"
        onChange={onFileInput}
      />

      {uploadedFiles.length > 0 && (
        <ul className="flex flex-col gap-2">
          {uploadedFiles.map(entry => (
            <FileListItem key={entry.id} entry={entry} onRemove={onRemove} />
          ))}
        </ul>
      )}
    </div>
  )
}
