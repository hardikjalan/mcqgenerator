'use client'

import { useEffect, useState, type ReactNode } from 'react'
import { LogOut, Menu, X, type LucideIcon } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { Logo } from '@/components/ui/Logo'
import { ThemeToggle } from '@/components/ui/ThemeToggle'

export type NavItem = {
  label: string
  /** Omit for sections that aren't built yet — renders disabled, never 404s. */
  href?: string
  Icon: LucideIcon
  /** Count shown on the right, e.g. number of drafts. */
  count?: number
}

export type ShellUser = { name: string; email: string; avatar: string; id: string }

/**
 * The frame every signed-in screen sits in: a nav rail on the left, a bar
 * across the top, content in the middle.
 *
 * Before this existed each dashboard drew its own header and there was no
 * navigation at all — every page was an island with no way to get anywhere.
 */
export function AppShell({
  nav,
  roleLabel,
  title,
  actions,
  children,
}: {
  nav: NavItem[]
  roleLabel: string
  title: string
  /** Buttons for the top bar, right of the title. */
  actions?: ReactNode
  children: ReactNode
}) {
  const [user, setUser] = useState<ShellUser | null>(null)
  const [menuOpen, setMenuOpen] = useState(false)

  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      if (!data.user) return
      setUser({
        id: data.user.id,
        name: data.user.user_metadata?.full_name ?? roleLabel,
        email: data.user.email ?? '',
        avatar: data.user.user_metadata?.avatar_url ?? '',
      })
    })
  }, [roleLabel])

  // Close the mobile drawer on Escape, and stop the page behind it scrolling.
  useEffect(() => {
    if (!menuOpen) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') setMenuOpen(false) }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [menuOpen])

  const handleSignOut = async () => {
    await createClient().auth.signOut()
    window.location.href = '/'
  }

  const railContent = (
    <>
      <div className="flex items-center gap-2.5 px-4 h-14 shrink-0">
        <Logo size={28} className="text-accent" />
        <span className="flex flex-col leading-none gap-1">
          <span className="text-xl font-bold tracking-tight text-text">Cognira</span>
          <span className="text-xs text-text-3">{roleLabel}</span>
        </span>
      </div>

      <nav className="flex-1 px-2.5 py-3 flex flex-col gap-0.5 overflow-y-auto">
        {nav.map(({ label, href, Icon, count }) => {
          const isCurrent = Boolean(href)
          return (
            <a
              key={label}
              href={href ?? undefined}
              aria-current={isCurrent ? 'page' : undefined}
              aria-disabled={!href}
              onClick={e => { if (!href) e.preventDefault() }}
              className={[
                'flex items-center gap-2.5 px-2.5 py-2 rounded-md text-base transition-colors',
                isCurrent
                  ? 'bg-accent-soft text-accent font-semibold'
                  : 'text-text-3 cursor-not-allowed',
              ].join(' ')}
            >
              <Icon className="w-4 h-4 shrink-0" aria-hidden="true" />
              <span className="flex-1 truncate">{label}</span>
              {count !== undefined && (
                <span className="text-xs tabular text-text-3">{count}</span>
              )}
              {!href && (
                <span className="text-xs px-1.5 py-0.5 rounded-sm bg-surface-2 text-text-3 font-medium">
                  Soon
                </span>
              )}
            </a>
          )
        })}
      </nav>

      <div className="p-2.5 border-t border-border-subtle shrink-0 flex flex-col gap-2">
        <div className="flex items-center gap-2.5 px-1.5 py-1 min-w-0">
          {user?.avatar ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={user.avatar} alt="" className="w-7 h-7 rounded-full shrink-0" />
          ) : (
            <span className="w-7 h-7 rounded-full bg-accent-soft text-accent text-xs font-bold flex items-center justify-center shrink-0">
              {(user?.name ?? '?').charAt(0).toUpperCase()}
            </span>
          )}
          <span className="flex flex-col min-w-0 leading-tight">
            <span className="text-sm font-semibold text-text truncate">{user?.name ?? 'Loading…'}</span>
            <span className="text-xs text-text-3 truncate">{user?.email}</span>
          </span>
        </div>
        <button
          onClick={handleSignOut}
          className="flex items-center gap-2.5 px-2.5 py-2 rounded-md text-base text-text-2 hover:bg-surface-2 hover:text-danger transition-colors cursor-pointer"
        >
          <LogOut className="w-4 h-4 shrink-0" aria-hidden="true" />
          Sign out
        </button>
      </div>
    </>
  )

  return (
    <div className="min-h-screen flex">

      {/* ── Rail (desktop) ────────────────────────────────────────────── */}
      <aside className="hidden lg:flex w-60 shrink-0 flex-col border-r border-border-subtle bg-surface sticky top-0 h-screen">
        {railContent}
      </aside>

      {/* ── Drawer (mobile) ───────────────────────────────────────────── */}
      {menuOpen && (
        <div className="lg:hidden fixed inset-0 z-40 flex">
          <div className="fixed inset-0 bg-text/40" onClick={() => setMenuOpen(false)} />
          <aside className="relative w-60 flex flex-col border-r border-border-subtle bg-surface h-full">
            {railContent}
          </aside>
        </div>
      )}

      {/* ── Content ───────────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-w-0">
        <header className="sticky top-0 z-30 h-14 shrink-0 flex items-center gap-3 px-4 sm:px-6 border-b border-border-subtle bg-surface/85 backdrop-blur">
          <button
            onClick={() => setMenuOpen(v => !v)}
            aria-label={menuOpen ? 'Close menu' : 'Open menu'}
            aria-expanded={menuOpen}
            className="lg:hidden relative z-50 p-1.5 -ml-1.5 rounded-md text-text-2 hover:bg-surface-2 cursor-pointer"
          >
            {menuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
          </button>

          <h1 className="text-md font-bold tracking-tight text-text truncate">{title}</h1>

          <div className="ml-auto flex items-center gap-3">
            {actions}
            <ThemeToggle />
          </div>
        </header>

        <main className="flex-1 px-4 sm:px-6 py-6">{children}</main>
      </div>
    </div>
  )
}
