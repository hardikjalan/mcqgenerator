'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { createClient } from '@/lib/supabase/client'
import { withTimeout } from '@/lib/async'

export type SessionUser = {
  id: string
  name: string
  email: string
  avatar: string
}

type UserState = { user: SessionUser | null; loading: boolean; error?: string }

const UserContext = createContext<UserState>({ user: null, loading: true })

/**
 * The signed-in user, fetched once per screen.
 *
 * Before this, the sidebar and the page each called getUser() separately — two
 * network round trips and two independent loading states on one screen. Read
 * from here instead of calling supabase.auth.getUser() in a page.
 */
export function useUser(): UserState {
  return useContext(UserContext)
}

export function UserProvider({
  fallbackName,
  children,
}: {
  /** Shown while the real name loads, e.g. the role label. */
  fallbackName: string
  children: ReactNode
}) {
  const [state, setState] = useState<UserState>({ user: null, loading: true })

  useEffect(() => {
    let cancelled = false

    withTimeout(() => createClient().auth.getUser()).then(({ data, error }) => {
      if (error) throw error
      if (cancelled) return
      const u = data.user
      setState({
        loading: false,
        user: u
          ? {
              id: u.id,
              name: u.user_metadata?.full_name ?? fallbackName,
              email: u.email ?? '',
              avatar: u.user_metadata?.avatar_url ?? '',
            }
          : null,
      })
    }).catch(error => {
      console.error('[account] User lookup failed:', error)
      if (!cancelled) setState({ user: null, loading: false, error: 'Could not load your account. Refresh the page or sign in again.' })
    })

    return () => { cancelled = true }
  }, [fallbackName])

  return <UserContext.Provider value={state}>{children}</UserContext.Provider>
}
