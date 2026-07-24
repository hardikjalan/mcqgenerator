import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')

  if (!code) {
    return NextResponse.redirect(`${origin}/?error=auth_failed`)
  }

  const supabase = await createClient()

  // Step 1: Exchange the OAuth code for a session
  const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
  if (exchangeError) {
    return NextResponse.redirect(`${origin}/?error=auth_failed`)
  }

  // Step 2: Get the authenticated user
  const { data: { user } } = await supabase.auth.getUser()
  if (!user?.email) {
    await supabase.auth.signOut()
    return NextResponse.redirect(`${origin}/?error=auth_failed`)
  }

  // Step 3: Sync non-sensitive profile metadata (name, avatar) on every login
  const { error: syncError } = await supabase.rpc('upsert_profile_on_login', {
    p_id:        user.id,
    p_email:     user.email,
    p_full_name: user.user_metadata?.full_name ?? null,
    p_avatar:    user.user_metadata?.avatar_url ?? null,
  })
  if (syncError) {
    console.error('Profile sync failed:', syncError.message)
    await supabase.auth.signOut()
    return NextResponse.redirect(`${origin}/?error=auth_failed`)
  }

  // Step 4: Read role — new users (role = NULL) go to onboarding
  const { data: profile } = await supabase
    .from('profiles')
    .select('role')
    .eq('id', user.id)
    .single()

  const role = profile?.role
  if (!role) {
    return NextResponse.redirect(`${origin}/onboarding`)
  }

  return NextResponse.redirect(`${origin}/dashboard/${role}`)
}
