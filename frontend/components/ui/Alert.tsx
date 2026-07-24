import type { ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Info, TriangleAlert } from 'lucide-react'

type Tone = 'error' | 'warning' | 'success' | 'info'

const TONES: Record<Tone, { box: string; Icon: typeof AlertCircle }> = {
  error:   { box: 'bg-danger-soft border-danger-line text-danger',    Icon: AlertCircle },
  warning: { box: 'bg-warning-soft border-warning-line text-warning', Icon: TriangleAlert },
  success: { box: 'bg-success-soft border-success-line text-success', Icon: CheckCircle2 },
  info:    { box: 'bg-accent-soft border-accent-line text-accent',    Icon: Info },
}

/**
 * Inline message attached to a form or action.
 *
 * Replaces the four hand-rolled alert boxes that were copy-pasted across the
 * login, onboarding and faculty pages — each with slightly different padding
 * and an emoji standing in for an icon.
 */
export function Alert({
  tone = 'error',
  children,
  className = '',
}: {
  tone?: Tone
  children: ReactNode
  className?: string
}) {
  const { box, Icon } = TONES[tone]

  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={`flex items-start gap-2.5 rounded-md border px-3.5 py-3 text-sm ${box} ${className}`}
    >
      <Icon className="w-4 h-4 mt-px shrink-0" aria-hidden="true" />
      <span className="leading-snug">{children}</span>
    </div>
  )
}
