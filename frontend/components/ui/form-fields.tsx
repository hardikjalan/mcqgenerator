// Form primitives — shared by every role's screens.

// ── SectionLabel ──────────────────────────────────────────────────────────────
// Numbered label used to group form fields into a visible sequence.
// Only use it where the steps genuinely run in order; a plain <Field label>
// is right for everything else.
export function SectionLabel({ step, children }: { step: number; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2.5 mb-2.5">
      <span className="w-5 h-5 rounded-full bg-accent-soft border border-accent-line text-accent text-xs font-bold flex items-center justify-center shrink-0 tabular">
        {step}
      </span>
      <span className="text-base font-semibold text-text">{children}</span>
    </div>
  )
}

// ── FormInput ─────────────────────────────────────────────────────────────────
const FIELD_CLASS =
  'w-full bg-surface border border-border-strong rounded-md px-3.5 py-2.5 text-base ' +
  'text-text placeholder:text-text-3 transition-colors duration-150 ' +
  'hover:border-text-3 focus:border-accent focus:outline-none ' +
  'focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-1'

type FormInputProps = {
  id: string
  placeholder: string
  value: string
  onChange: (value: string) => void
  multiline?: boolean
  rows?: number
}

export function FormInput({ id, placeholder, value, onChange, multiline = false, rows = 3 }: FormInputProps) {
  return multiline ? (
    <textarea
      id={id}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className={`${FIELD_CLASS} resize-none leading-relaxed`}
    />
  ) : (
    <input
      id={id}
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      className={FIELD_CLASS}
    />
  )
}

// ── Field ─────────────────────────────────────────────────────────────────────
// Label + control + optional hint, wired so clicking the label focuses the
// input and screen readers announce the hint alongside it.
export function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string
  label: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold text-text-2">
        {label}
      </label>
      {children}
      {hint && (
        <p id={`${id}-hint`} className="text-xs text-text-3">
          {hint}
        </p>
      )}
    </div>
  )
}
