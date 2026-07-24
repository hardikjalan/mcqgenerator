import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

/**
 * OAuth callback.
 *
 * Rule for this route: the only things that may fail a sign-in are a missing
 * or unusable code, and an account with no email address. Everything else —
 * syncing the display name, reading the profile row — is best-effort. A
 * cosmetic write must never cost the user their session.
 *
 * That rule exists because it was broken: a failed metadata sync used to call
 * signOut() and bounce to ?error=auth_failed. It only ever failed on a brand
 * new account (the INSERT path), which is why the first sign-in appeared to
 * fail and the second worked — the first attempt had already created the row.
 */

/** The profile row is created by a trigger on auth.users. On a first sign-in
 *  that row can land a moment after the session does, so a miss is retried
 *  once before we treat it as genuinely absent. */
async function readRole(
  supabase: Awaited<ReturnType<typeof createClient>>,
  userId: string
): Promise<string | null> {
  for (let attempt = 0; attempt < 2; attempt++) {
    const { data, error } = await supabase
      .from('profiles')
      .select('role')
      .eq('id', userId)
      .maybeSingle()

    if (error) {
      console.error('[auth/callback] Profile read failed:', error.message)
      return null
    }
    if (data) return data.role ?? null
    if (attempt === 0) await new Promise(r => setTimeout(r, 250))
  }

  console.warn('[auth/callback] No profile row for user', userId, '— sending to onboarding')
  return null
}

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)

  // The provider can refuse before we ever get a code — e.g. the user closed
  // the Google consent screen. Surface that instead of a generic failure.
  const providerError = searchParams.get('error')
  if (providerError) {
    console.error(
      '[auth/callback] Provider returned an error:',
      providerError,
      searchParams.get('error_description') ?? ''
    )
    return NextResponse.redirect(`${origin}/?error=cancelled`)
  }

  const code = searchParams.get('code')
  if (!code) {
    console.error('[auth/callback] No code in callback URL')
    return NextResponse.redirect(`${origin}/?error=auth_failed`)
  }

  const supabase = await createClient()

  // ── 1. Exchange the code for a session ─────────────────────────────────────
  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
  if (exchangeError) {
    // This is the message that actually tells you what went wrong — a expired
    // code, a missing PKCE verifier cookie, or a database error while the
    // account was being created.
    console.error('[auth/callback] Code exchange failed:', exchangeError.message)
    return NextResponse.redirect(`${origin}/?error=auth_failed`)
  }

  // ── 2. Confirm we have a usable account ────────────────────────────────────
  const { data: { user }, error: userError } = await supabase.auth.getUser()
  if (userError || !user) {
    console.error('[auth/callback] No user after exchange:', userError?.message ?? 'user was null')
    return NextResponse.redirect(`${origin}/?error=auth_failed`)
  }
  if (!user.email) {
    // Genuinely fatal: profiles.email is NOT NULL, so there's nothing to create.
    console.error('[auth/callback] Google account has no email address:', user.id)
    await supabase.auth.signOut()
    return NextResponse.redirect(`${origin}/?error=no_email`)
  }

  // ── 3. Refresh name and avatar — best effort, never fatal ──────────────────
  const profileFields = {
    id: user.id,
    email: user.email,
    full_name: user.user_metadata?.full_name ?? null,
    avatar_url: user.user_metadata?.avatar_url ?? null,
  }

  const { error: syncError } = await supabase.rpc('upsert_profile_on_login', {
    p_id: profileFields.id,
    p_email: profileFields.email,
    p_full_name: profileFields.full_name,
    p_avatar: profileFields.avatar_url,
  })

  if (syncError) {
    console.error('[auth/callback] upsert_profile_on_login failed:', syncError.message)

    // Fall back to a direct upsert. RLS allows a user to write their own row
    // (profiles_insert_own / profiles_update_own), so this works even if the
    // RPC is missing or the trigger never created the row. It deliberately
    // omits `role`, which the user is not permitted to set.
    const { error: fallbackError } = await supabase
      .from('profiles')
      .upsert(profileFields, { onConflict: 'id' })

    if (fallbackError) {
      // Still not fatal. The session is valid; onboarding creates the row.
      console.error('[auth/callback] Fallback profile upsert failed:', fallbackError.message)
    }
  }

  // ── 4. Route on role — no role yet means onboarding ────────────────────────
  const role = await readRole(supabase, user.id)
  return NextResponse.redirect(role ? `${origin}/dashboard/${role}` : `${origin}/onboarding`)
}
