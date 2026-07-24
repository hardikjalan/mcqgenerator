'use client'

import { useRef } from 'react'
import { CloudUpload, X, CheckCircle2, AlertCircle, Loader2, FileText, FileImage, FileSpreadsheet } from 'lucide-react'
import type { UploadedFile } from '@/types/upload'
import { ALLOWED_EXTENSIONS, formatBytes, getFileExt } from '@/lib/file-upload'

// ── File type icon (uses lucide) ──────────────────────────────────────────────
function FileTypeIcon({ ext }: { ext: string }) {
  if (ext === 'pdf') return <FileText className="w-5 h-5 text-rose-400 flex-shrink-0" />
  if (ext === 'docx') return <FileText className="w-5 h-5 text-sky-400 flex-shrink-0" />
  if (ext === 'pptx') return <FileSpreadsheet className="w-5 h-5 text-orange-400 flex-shrink-0" />
  return <FileImage className="w-5 h-5 text-emerald-400 flex-shrink-0" />
}

// ── Single file row ───────────────────────────────────────────────────────────
function FileListItem({ entry, onRemove }: { entry: UploadedFile; onRemove: (e: UploadedFile) => void }) {
  return (
    <div className={`flex items-center gap-3 px-4 py-3 rounded-xl border transition-colors ${
      entry.status === 'error'
        ? 'border-rose-500/20 bg-rose-500/5'
        : entry.status === 'done'
        ? 'border-emerald-500/15 bg-emerald-500/4'
        : 'border-slate-800/70 bg-slate-900/30'
    }`}>
      <FileTypeIcon ext={getFileExt(entry.file.name)} />

      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-0.5">
          <span className="text-xs font-medium text-slate-200 truncate">{entry.file.name}</span>
          <span className="text-[10px] text-slate-600 whitespace-nowrap flex-shrink-0">{formatBytes(entry.file.size)}</span>
        </div>

        {entry.status === 'uploading' && (
          <div className="space-y-1">
            <div className="h-[3px] w-full bg-slate-800 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full transition-all duration-200"
                style={{ width: `${entry.progress}%` }}
              />
            </div>
            <div className="flex items-center gap-1.5">
              <Loader2 className="w-3 h-3 text-indigo-400 animate-spin" />
              <span className="text-[10px] text-indigo-400">Uploading {entry.progress}%</span>
            </div>
          </div>
        )}

        {entry.status === 'done' && (
          <div className="flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span className="text-[10px] text-emerald-400">Ready</span>
          </div>
        )}

        {entry.status === 'error' && (
          <div className="flex items-center gap-1">
            <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
            <span className="text-[10px] text-rose-400">{entry.errorMsg}</span>
          </div>
        )}
      </div>

      <button
        onClick={() => onRemove(entry)}
        className="p-1.5 rounded-lg text-slate-600 hover:text-rose-400 hover:bg-rose-500/10 transition-all cursor-pointer flex-shrink-0"
        title="Remove file"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  )
}

// ── Drop Zone ─────────────────────────────────────────────────────────────────
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
    <div className="space-y-4">
      {/* Drop target */}
      <div
        id="file-drop-zone"
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`rounded-2xl border-2 border-dashed py-14 flex flex-col items-center gap-4 cursor-pointer transition-all duration-300 ${
          isDragging
            ? 'border-indigo-500/70 bg-indigo-500/8 scale-[1.005]'
            : 'border-slate-800 hover:border-indigo-500/35 hover:bg-indigo-500/4'
        }`}
      >
        <CloudUpload
          className={`w-9 h-9 text-indigo-400/80 transition-transform duration-300 ${isDragging ? 'scale-110 -translate-y-1' : ''}`}
        />
        <div className="text-center">
          <p className="text-sm font-semibold text-slate-300">
            {isDragging ? 'Release to upload' : 'Drag & drop your files here'}
          </p>
          <p className="text-xs text-slate-600 mt-1">or click to browse · max 5 MB per file · 5 MB total</p>
        </div>
        <div className="flex gap-1.5">
          {['PDF', 'DOCX', 'PPTX', 'PNG', 'JPG'].map(ext => (
            <span
              key={ext}
              className="px-2 py-0.5 text-[9px] font-bold rounded-md bg-slate-800/80 border border-slate-700/60 text-slate-500 uppercase tracking-wider"
            >
              {ext}
            </span>
          ))}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept={ALLOWED_EXTENSIONS.join(',')}
          className="hidden"
          onChange={onFileInput}
        />
      </div>

      {/* File list */}
      {uploadedFiles.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] text-slate-600 uppercase font-bold tracking-wider px-1">
            {uploadedFiles.length} file{uploadedFiles.length !== 1 ? 's' : ''}
          </p>
          {uploadedFiles.map(entry => (
            <FileListItem key={entry.id} entry={entry} onRemove={onRemove} />
          ))}
        </div>
      )}
    </div>
  )
}
