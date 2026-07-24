import { cloneElement, isValidElement, type ReactElement, type ReactNode } from 'react'

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
  /** Set by <Field> so the hint is read out with the input. Don't pass by hand. */
  'aria-describedby'?: string
}

export function FormInput({
  id,
  placeholder,
  value,
  onChange,
  multiline = false,
  rows = 3,
  'aria-describedby': describedBy,
}: FormInputProps) {
  return multiline ? (
    <textarea
      id={id}
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      aria-describedby={describedBy}
      className={`${FIELD_CLASS} resize-none leading-relaxed`}
    />
  ) : (
    <input
      id={id}
      type="text"
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder}
      aria-describedby={describedBy}
      className={FIELD_CLASS}
    />
  )
}

// ── Field ─────────────────────────────────────────────────────────────────────
/**
 * Label + control + optional hint.
 *
 * The hint is attached to the control with aria-describedby, so a screen reader
 * reads it as part of the field instead of skipping it. Field does that wiring
 * itself — callers just pass `hint` and never think about it.
 */
export function Field({
  id,
  label,
  hint,
  children,
}: {
  id: string
  label: string
  hint?: string
  children: ReactNode
}) {
  const hintId = hint ? `${id}-hint` : undefined

  const control =
    hintId && isValidElement(children)
      ? cloneElement(children as ReactElement<{ 'aria-describedby'?: string }>, {
          'aria-describedby': hintId,
        })
      : children

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-semibold text-text-2">
        {label}
      </label>
      {control}
      {hint && (
        <p id={hintId} className="text-xs text-text-3">
          {hint}
        </p>
      )}
    </div>
  )
}
