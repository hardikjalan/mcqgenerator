import type { ReactNode } from 'react'

/**
 * A raised surface. The default container for anything that groups content.
 *
 * Depth comes from a real border plus a soft shadow — not from a blur or a
 * coloured glow, which is what made the old screens read as decoration.
 */
export function Card({
  children,
  className = '',
  padded = true,
}: {
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <section
      className={[
        'bg-surface border border-border-subtle rounded-lg shadow-sm',
        padded ? 'p-5' : '',
        className,
      ].join(' ')}
    >
      {children}
    </section>
  )
}

/** Title row for a Card. `aside` sits right-aligned — counts, status, actions. */
export function CardHeader({
  title,
  hint,
  aside,
}: {
  title: string
  hint?: string
  aside?: ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4 pb-3 mb-4 border-b border-border-subtle">
      <div className="flex flex-col gap-0.5 min-w-0">
        <h2 className="text-md font-bold text-text tracking-tight">{title}</h2>
        {hint && <p className="text-sm text-text-3">{hint}</p>}
      </div>
      {aside && <div className="shrink-0">{aside}</div>}
    </div>
  )
}
