import { NextResponse } from 'next/server'
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')

  if (code) {
    const cookieStore = await cookies()
    const supabase = createServerClient(
      process.env.NEXT_PUBLIC_SUPABASE_URL!,
      process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
      {
        cookies: {
          getAll() {
            return cookieStore.getAll()
          },
          setAll(cookiesToSet) {
            try {
              cookiesToSet.forEach(({ name, value, options }) =>
                cookieStore.set(name, value, options)
              )
            } catch {
              // Ignore if called from Server Component
            }
          },
        },
      }
    )

    // Step 1: Exchange the Google code for a Supabase session.
    // This also triggers the handle_new_user DB trigger which creates
    // the profile row and assigns the role based on email domain.
    const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
    if (exchangeError) {
      return NextResponse.redirect(`${origin}/?error=auth_failed`)
    }

    // Step 2: Get the authenticated user
    const { data: { user } } = await supabase.auth.getUser()

    if (!user?.email) {
      await supabase.auth.signOut()
      return NextResponse.redirect(`${origin}/?error=no_email`)
    }

    // Step 3: Sync profile metadata (name, avatar) via secure RPC.
    // Role is NOT passed here — it is owned entirely by the DB trigger.
    // The RPC only updates non-sensitive metadata on every login.
    const { error: upsertError } = await supabase.rpc('upsert_profile_on_login', {
      p_id:        user.id,
      p_email:     user.email,
      p_full_name: user.user_metadata?.full_name ?? null,
      p_avatar:    user.user_metadata?.avatar_url ?? null,
    })

    if (upsertError) {
      console.error('Profile sync failed:', upsertError.message)
      await supabase.auth.signOut()
      return NextResponse.redirect(`${origin}/?error=db_error`)
    }

    // Step 4: Read the role assigned by the DB trigger (single source of truth).
    // If the email domain was not recognized, the trigger sets role = NULL.
    const { data: profile } = await supabase
      .from('profiles')
      .select('role')
      .eq('id', user.id)
      .single()

    const role = profile?.role

    if (!role) {
      // Unauthorized email domain — DB trigger did not assign a role
      await supabase.auth.signOut()
      return NextResponse.redirect(`${origin}/?error=unauthorized_domain`)
    }

    // Step 5: Route to role-specific dashboard
    return NextResponse.redirect(`${origin}/dashboard/${role}`)
  }

  return NextResponse.redirect(`${origin}/?error=auth_failed`)
}
