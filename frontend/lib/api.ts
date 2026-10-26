import { apiUrl } from '@/lib/env'
import { createClient } from '@/lib/supabase/client'

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const { data: { session } } = await createClient().auth.getSession()
  if (!session) throw new Error('Your session expired. Please sign in again.')
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${session.access_token}`)
  if (init.body) headers.set('Content-Type', 'application/json')
  const response = await fetch(apiUrl(path), { ...init, headers, cache: 'no-store' })
  const result = await response.json().catch(() => null)
  if (!response.ok) throw new Error(result?.error ?? `Request failed (${response.status}). Please retry.`)
  return result as T
}

export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Something went wrong. Please try again.'
}
