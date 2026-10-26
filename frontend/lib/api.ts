import { apiUrl } from '@/lib/env'
import { createClient } from '@/lib/supabase/client'
import { withTimeout } from '@/lib/async'

export async function apiRequest<T>(path: string, init: RequestInit = {}, timeoutMs = 30000): Promise<T> {
  try {
    return await withTimeout(async signal => {
      const { data: { session } } = await createClient().auth.getSession()
      if (!session) throw new Error('Your session expired. Please sign in again.')
      const headers = new Headers(init.headers)
      headers.set('Authorization', `Bearer ${session.access_token}`)
      if (init.body) headers.set('Content-Type', 'application/json')
      const response = await fetch(apiUrl(path), { ...init, headers, cache: 'no-store',
        signal: init.signal ? AbortSignal.any([init.signal, signal]) : signal })
      const result = await response.json().catch(() => null)
      if (!response.ok) throw new Error(result?.error ?? `Request failed (${response.status}). Please retry.`)
      if (result === null && response.status !== 204) throw new Error('The server returned an unreadable response. Please retry.')
      return result as T
    }, timeoutMs)
  } catch (error) {
    if (error instanceof TypeError) {
      console.error('[api] Network request failed:', error.message)
      throw new Error('Could not reach the assessment server. Check your connection and try again.')
    }
    throw error
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}
