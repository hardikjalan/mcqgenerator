import { createBrowserClient } from '@supabase/ssr'
import { SUPABASE_ANON_KEY, SUPABASE_URL } from '@/lib/env'
import { boundedFetch } from '@/lib/async'

/** Supabase client for browser ('use client') components. */
export function createClient() {
  return createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY, { global: { fetch: boundedFetch } })
}
