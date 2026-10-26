import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { SUPABASE_ANON_KEY, SUPABASE_URL } from '@/lib/env'

export async function proxy(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const supabase = createServerClient(
    SUPABASE_URL,
    SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() { return request.cookies.getAll() },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  // Refresh session (required by @supabase/ssr to keep cookies alive)
  const { data: { user } } = await supabase.auth.getUser()
  const pathname = request.nextUrl.pathname
  const redirect = (path: string) => {
    const response = NextResponse.redirect(new URL(path, request.url))
    for (const cookie of supabaseResponse.cookies.getAll()) response.cookies.set(cookie)
    return response
  }

  // ── Rule 1: Logged-out user → redirect to login ──────────────────────────
  if (!user) {
    return redirect('/')
  }

  // ── Rule 2: Logged-in user — read their role ─────────────────────────────
  // maybeSingle() instead of single(): on a brand-new account the profile row
  // may not exist yet (the DB trigger is still running). single() would throw
  // PGRST116 and poison the role lookup; maybeSingle() returns null cleanly,
  // which Rule 3 below handles by redirecting to /onboarding.
  const { data: profile, error: profileError } = await supabase
    .from('profiles')
    .select('role,suspended')
    .eq('id', user.id)
    .maybeSingle()

  if (profileError) {
    console.error('[proxy] Profile role query failed:', profileError.message, profileError.code)
  }

  const role = profile?.role
  if (profile?.suspended) return redirect('/?error=suspended')

  // ── Rule 3: No role yet → must complete onboarding ───────────────────────
  if (!role) {
    if (pathname !== '/onboarding') {
      return redirect('/onboarding')
    }
    return supabaseResponse
  }

  // ── Rule 4: Already onboarded → block /onboarding (go to dashboard) ──────
  if (pathname === '/onboarding') {
    return redirect(`/dashboard/${role}`)
  }

  // ── Rule 5: Enforce role-specific dashboard access ────────────────────────
  if (pathname.startsWith('/dashboard')) {
    const allowedPrefix = `/dashboard/${role}`
    if (pathname !== allowedPrefix && !pathname.startsWith(`${allowedPrefix}/`)) {
      return redirect(allowedPrefix)
    }
  }

  return supabaseResponse
}

// Run proxy on dashboard and onboarding routes
export const config = {
  matcher: ['/dashboard/:path*', '/onboarding'],
}
