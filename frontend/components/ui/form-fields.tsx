// Reusable form field primitives — shared across all dashboard pages

// ── SectionLabel ──────────────────────────────────────────────────────────────
// Numbered label used to visually group form fields in a step-by-step layout
export function SectionLabel({ step, children }: { step: number; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 mb-3">
      <span className="w-6 h-6 rounded-full bg-indigo-500/20 border border-indigo-500/30 text-indigo-400 text-[10px] font-bold flex items-center justify-center flex-shrink-0">
        {step}
      </span>
      <span className="text-sm font-semibold text-slate-200">{children}</span>
    </div>
  )
}

// ── FormInput ─────────────────────────────────────────────────────────────────
// Single-line or multi-line text input with consistent dark styling
type FormInputProps = {
  id: string
  placeholder: string
  value: string
  onChange: (value: string) => void
  multiline?: boolean
  rows?: number
}

export function FormInput({ id, placeholder, value, onChange, multiline = false, rows = 3 }: FormInputProps) {
  const cls =
    'w-full bg-[#0b0f1a] border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-100 ' +
    'placeholder:text-slate-600 focus:outline-none focus:border-indigo-500/70 focus:bg-[#0d1120] ' +
    'transition-all duration-200 leading-relaxed'

  return multiline ? (
    <textarea
      id={id}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className={`${cls} resize-none`}
    />
  ) : (
    <input
      id={id}
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className={cls}
    />
  )
}
