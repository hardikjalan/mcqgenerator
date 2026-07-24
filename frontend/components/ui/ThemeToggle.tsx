'use client'

import { useSyncExternalStore } from 'react'
import { Monitor, Moon, Sun } from 'lucide-react'

export type Theme = 'light' | 'dark' | 'system'

const STORAGE_KEY = 'cognira-theme'
const CHANGE_EVENT = 'cognira-theme-change'

const OPTIONS: { key: Theme; label: string; Icon: typeof Sun }[] = [
  { key: 'light',  label: 'Light',  Icon: Sun },
  { key: 'system', label: 'System', Icon: Monitor },
  { key: 'dark',   label: 'Dark',   Icon: Moon },
]

/**
 * 'system' removes the attribute, so `color-scheme: light dark` on :root hands
 * the decision back to the operating system.
 */
function applyToDom(theme: Theme) {
  if (theme === 'system') delete document.documentElement.dataset.theme
  else document.documentElement.dataset.theme = theme
}

// ── The theme lives on <html>, not in React state ────────────────────────────
// An inline script in layout.tsx sets it before first paint to avoid a flash of
// the wrong theme, so React is never the owner. useSyncExternalStore lets the
// component read that outside value without mirroring it into state.

function subscribe(onChange: () => void) {
  // Fired by this tab when the user picks a theme.
  window.addEventListener(CHANGE_EVENT, onChange)

  // Fired by *other* tabs. They only get the storage write, so apply it here
  // too — otherwise a second tab keeps rendering the old theme.
  const onStorage = (e: StorageEvent) => {
    if (e.key !== STORAGE_KEY) return
    applyToDom(e.newValue === 'light' || e.newValue === 'dark' ? e.newValue : 'system')
    onChange()
  }
  window.addEventListener('storage', onStorage)

  return () => {
    window.removeEventListener(CHANGE_EVENT, onChange)
    window.removeEventListener('storage', onStorage)
  }
}

function getSnapshot(): Theme {
  const t = document.documentElement.dataset.theme
  return t === 'light' || t === 'dark' ? t : 'system'
}

/** No DOM on the server — render the neutral option and let hydration correct it. */
function getServerSnapshot(): Theme {
  return 'system'
}

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  const choose = (next: Theme) => {
    applyToDom(next)
    try {
      if (next === 'system') localStorage.removeItem(STORAGE_KEY)
      else localStorage.setItem(STORAGE_KEY, next)
    } catch {
      // Private browsing can refuse storage — the theme still applies for
      // this page, it just won't be remembered.
    }
    window.dispatchEvent(new Event(CHANGE_EVENT))
  }

  return (
    <div
      role="radiogroup"
      aria-label="Colour theme"
      className="inline-flex items-center gap-0.5 p-0.5 rounded-md bg-surface-2 border border-border-subtle"
    >
      {OPTIONS.map(({ key, label, Icon }) => {
        const active = theme === key
        return (
          <button
            key={key}
            role="radio"
            aria-checked={active}
            aria-label={label}
            title={label}
            onClick={() => choose(key)}
            className={[
              'w-7 h-7 rounded-sm flex items-center justify-center cursor-pointer transition-colors',
              active ? 'bg-surface text-accent shadow-sm' : 'text-text-3 hover:text-text-2',
            ].join(' ')}
          >
            <Icon className="w-3.5 h-3.5" aria-hidden="true" />
          </button>
        )
      })}
    </div>
  )
}
