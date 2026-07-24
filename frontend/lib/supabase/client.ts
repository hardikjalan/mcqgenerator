import { createBrowserClient } from '@supabase/ssr'

export function createClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

  if (!url || !key) {
    throw new Error('Supabase client credentials are missing! Make sure NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY are set in your .env.local.')
  }

  // Ensure base URL doesn't end with rest/v1/
  const baseUrl = url.replace(/\/rest\/v1\/?$/, '')

  return createBrowserClient(baseUrl, key)
}
