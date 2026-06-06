import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function proxy(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
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

  // Refresh session (required to keep session alive with @supabase/ssr)
  const { data: { user } } = await supabase.auth.getUser()

  const pathname = request.nextUrl.pathname

  // ── Rule 1: Not logged in → redirect to login ────────────────────────────
  if (!user && pathname.startsWith('/dashboard')) {
    return NextResponse.redirect(new URL('/', request.url))
  }

  // ── Rule 2: Logged in → enforce role-based access ────────────────────────
  if (user && pathname.startsWith('/dashboard')) {
    const { data: profile } = await supabase
      .from('profiles')
      .select('role')
      .eq('id', user.id)
      .single()

    const role = profile?.role

    // Role not set in DB yet → send to home with error
    if (!role) {
      await supabase.auth.signOut()
      return NextResponse.redirect(new URL('/?error=no_role', request.url))
    }

    // Enforce role-specific path access
    const allowedPrefix = `/dashboard/${role}`
    if (!pathname.startsWith(allowedPrefix)) {
      return NextResponse.redirect(new URL(allowedPrefix, request.url))
    }
  }

  return supabaseResponse
}

// Only run proxy on dashboard routes
export const config = {
  matcher: ['/dashboard/:path*'],
}
