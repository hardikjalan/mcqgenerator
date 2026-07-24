import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { Spinner } from './Spinner'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-accent text-on-accent border border-transparent hover:bg-accent-hover active:bg-accent-active',
  secondary:
    'bg-surface text-text border border-border-strong hover:bg-surface-2 hover:border-text-3',
  ghost:
    'bg-transparent text-text-2 border border-transparent hover:bg-surface-2 hover:text-text',
  danger:
    'bg-danger-soft text-danger border border-danger-line hover:bg-danger hover:text-white',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-sm',
  md: 'h-10 px-4 text-base gap-2 rounded-md',
  lg: 'h-12 px-5 text-md gap-2.5 rounded-md',
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant
  size?: Size
  loading?: boolean
  /** Fill the container. Use for the single main action on a card or form. */
  block?: boolean
  children: ReactNode
}

export function Button({
  variant = 'primary',
  size = 'md',
  loading = false,
  block = false,
  disabled,
  className = '',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={[
        'inline-flex items-center justify-center font-semibold whitespace-nowrap',
        'transition-colors duration-150 cursor-pointer',
        'disabled:opacity-45 disabled:cursor-not-allowed disabled:hover:bg-inherit',
        VARIANTS[variant],
        SIZES[size],
        block ? 'w-full' : '',
        className,
      ].join(' ')}
    >
      {loading && <Spinner size={size === 'sm' ? 13 : 15} />}
      {children}
    </button>
  )
}
