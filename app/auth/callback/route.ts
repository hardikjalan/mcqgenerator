import { NextResponse } from 'next/server'
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

// ── Explicit Email Roles ──────────────────────────────────────────────────────
// Add specific email addresses here to bypass domain checks and assign a role directly.
const ADMIN_EMAILS: string[] = [
  // E.g., 'admin@vit.ac.in'
]

const FACULTY_EMAILS: string[] = [
  'hardikjalan2005@gmail.com', // Override to test as faculty
]

const STUDENT_EMAILS: string[] = [
  // E.g., 'override_student@gmail.com'
]

// ── Domain → Role mapping ─────────────────────────────────────────────────────
const ALLOWED_DOMAINS: Record<string, 'student' | 'faculty' | 'admin'> = {
  'vitstudent.ac.in': 'student',
  'vit.ac.in': 'faculty',
}

function getRoleFromEmail(email: string): 'student' | 'faculty' | 'admin' | null {
  const cleanEmail = email.trim().toLowerCase()

  if (ADMIN_EMAILS.includes(cleanEmail)) return 'admin'
  if (FACULTY_EMAILS.includes(cleanEmail)) return 'faculty'
  if (STUDENT_EMAILS.includes(cleanEmail)) return 'student'

  const domain = cleanEmail.split('@')[1]
  return ALLOWED_DOMAINS[domain] ?? null
}

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

    // Step 1: Exchange the Google code for a Supabase session
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

    // Step 3: Validate email domain
    const role = getRoleFromEmail(user.email)

    if (!role) {
      // Not a VIT email — sign them out immediately and redirect with error
      await supabase.auth.signOut()
      return NextResponse.redirect(`${origin}/?error=unauthorized_domain`)
    }

    // Step 4: Upsert their profile with the detected role
    const { error: upsertError } = await supabase.from('profiles').upsert({
      id: user.id,
      email: user.email,
      full_name: user.user_metadata?.full_name ?? null,
      avatar_url: user.user_metadata?.avatar_url ?? null,
      role,
    })

    if (upsertError) {
      console.error('Database profile upsert failed:', upsertError)
      await supabase.auth.signOut()
      return NextResponse.redirect(`${origin}/?error=db_error&message=${encodeURIComponent(upsertError.message)}`)
    }

    // Step 5: Route them to their role-specific dashboard
    return NextResponse.redirect(`${origin}/dashboard/${role}`)
  }

  return NextResponse.redirect(`${origin}/?error=auth_failed`)
}
