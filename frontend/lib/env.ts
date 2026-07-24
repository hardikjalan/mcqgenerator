/**
 * env.ts
 * ─────────────────────────────────────────────────────────────────────────────
 * Every environment value the frontend reads, checked in one place.
 *
 * Why one file: the browser client, the server client and proxy.ts each used to
 * read process.env themselves, and they had drifted — one accepted a second key
 * name and trimmed the URL, the others didn't, and proxy.ts used `!` to silence
 * TypeScript rather than check anything. Now there is one copy and it cannot
 * disagree with itself.
 *
 * Only NEXT_PUBLIC_* values belong here — anything in this file is compiled
 * into the browser bundle and is readable by anyone. Server-side secrets live
 * in backend/.env and never reach this app.
 */

function required(name: string, value: string | undefined): string {
  if (!value) {
    throw new Error(
      `Missing ${name}.\n` +
        `  Local:  copy frontend/.env.example to frontend/.env.local and fill it in.\n` +
        `  Vercel: Project Settings → Environment Variables. The build reads these, ` +
        `so add it and redeploy — restarting isn't enough.`
    )
  }
  return value
}

/** Guards against pasting the full REST endpoint instead of the project URL. */
function normaliseSupabaseUrl(url: string): string {
  return url.replace(/\/rest\/v1\/?$/, '').replace(/\/$/, '')
}

export const SUPABASE_URL = normaliseSupabaseUrl(
  required('NEXT_PUBLIC_SUPABASE_URL', process.env.NEXT_PUBLIC_SUPABASE_URL)
)

// Supabase renamed "anon key" to "publishable key". Accept either so a project
// created under the newer naming works without editing code.
export const SUPABASE_ANON_KEY = required(
  'NEXT_PUBLIC_SUPABASE_ANON_KEY',
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
)

/**
 * Where the FastAPI backend lives.
 *
 * Falls back to localhost in development only. In a deployed build an unset
 * value stays empty on purpose, so apiUrl() throws something readable instead
 * of the app quietly trying to reach the user's own machine.
 */
const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ??
  (process.env.NODE_ENV === 'production' ? '' : 'http://localhost:8000')

/** Build a backend URL. `apiUrl('/generate-assessment')` */
export function apiUrl(path: string): string {
  if (!API_BASE) {
    throw new Error(
      'NEXT_PUBLIC_API_URL is not set. Point it at the deployed backend, e.g. https://api.example.com'
    )
  }
  return `${API_BASE.replace(/\/$/, '')}${path.startsWith('/') ? path : `/${path}`}`
}
