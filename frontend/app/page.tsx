'use client'

import { useState, useEffect, useCallback, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { FileText, PencilLine, BarChart3, X } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { Wordmark } from '@/components/ui/Logo'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'
import { ThemeToggle } from '@/components/ui/ThemeToggle'

const GoogleIcon = () => (
  <svg viewBox="0 0 24 24" width="18" height="18" className="shrink-0" aria-hidden="true">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
  </svg>
)

// What the product actually does, in the order you do it.
const STEPS = [
  { Icon: FileText,  title: 'Add your material', body: 'Upload lecture slides, notes or a PDF.' },
  { Icon: PencilLine, title: 'Review the questions', body: 'Cognira drafts them. You edit anything that isn’t right before it goes out.' },
  { Icon: BarChart3, title: 'See how it went', body: 'Results per student and per topic, so you know what to teach again.' },
]

const ERROR_MESSAGES: Record<string, string> = {
  auth_failed: 'Sign-in didn’t complete. Please try again.',
  cancelled: 'Sign-in was cancelled. Pick your Google account to continue.',
  no_email: 'We couldn’t read the email address on that Google account. Try signing in with a different one.',
  no_role: 'We couldn’t work out whether you’re a student or a teacher. Contact support and we’ll fix it.',
  db_error: 'Something went wrong setting up your account. Try signing in again — if it keeps happening, contact support.',
}

// ── Reads ?error= from the URL. Needs Suspense because of useSearchParams. ───
function ErrorFromUrl({ onError }: { onError: (msg: string) => void }) {
  const searchParams = useSearchParams()

  useEffect(() => {
    const urlError = searchParams.get('error')
    if (urlError && ERROR_MESSAGES[urlError]) onError(ERROR_MESSAGES[urlError])
  }, [searchParams, onError])

  return null
}

type ModalKey = 'terms' | 'privacy' | 'support'

export default function LoginPage() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [modal, setModal] = useState<ModalKey | null>(null)

  const closeModal = useCallback(() => setModal(null), [])

  // Escape closes the dialog, and the page behind it stops scrolling while
  // it's open. Neither worked before.
  useEffect(() => {
    if (!modal) return
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') closeModal() }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [modal, closeModal])

  const handleGoogleLogin = async () => {
    try {
      setIsLoading(true)
      setError(null)
      const supabase = createClient()
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`,
          queryParams: { prompt: 'select_account' },
        },
      })
      if (error) throw error
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Sign-in didn’t complete. Please try again.')
      setIsLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen flex flex-col">
      <Suspense fallback={null}>
        <ErrorFromUrl onError={setError} />
      </Suspense>

      {/* One soft tint at the top so the page isn't a flat slab. */}
      <div
        className="absolute inset-x-0 top-0 h-80 -z-10 pointer-events-none"
        style={{ background: 'linear-gradient(180deg, var(--wash-top), var(--bg))' }}
        aria-hidden="true"
      />

      {/* ── Header ───────────────────────────────────────────────────────── */}
      {/* The wordmark moved down into the column with the headline, so the
          header only carries the theme switch. */}
      <header className="w-full max-w-5xl mx-auto px-5 sm:px-8 h-16 flex items-center justify-end">
        <ThemeToggle />
      </header>

      <main className="flex-1 w-full max-w-5xl mx-auto px-5 sm:px-8 py-10 sm:py-16 grid lg:grid-cols-[minmax(0,1fr)_minmax(0,368px)] gap-10 lg:gap-14 items-center">

        {/* ── Left: what it is ───────────────────────────────────────────── */}
        <div className="flex flex-col gap-7 max-w-lg">
          <div className="flex flex-col gap-3.5">
            {/* Brand sits above the headline and outranks it — 38px against
                30px. The mark-to-text ratio inside the lockup stays 0.8. */}
            <Wordmark size={48} className="mb-2" />
            <h1 className="text-3xl font-extrabold tracking-tight text-text leading-[1.15] text-balance">
              Your slides, turned into a quiz in a couple of minutes.
            </h1>
            <p className="text-md text-text-2 leading-relaxed">
              Upload a lecture PDF or deck. Cognira reads it and drafts the questions.
              You check them, then send them to your class.
            </p>
          </div>

          <ol className="flex flex-col gap-3.5">
            {STEPS.map(({ Icon, title, body }, i) => (
              <li key={title} className="flex gap-3">
                <span className="relative w-7 h-7 rounded-md bg-accent-soft border border-accent-line text-accent flex items-center justify-center shrink-0">
                  <Icon className="w-3.5 h-3.5" aria-hidden="true" />
                  {/* Line joining the steps, so they read as a sequence */}
                  {i < STEPS.length - 1 && (
                    <span className="absolute top-full left-1/2 w-px h-3.5 bg-border-strong" aria-hidden="true" />
                  )}
                </span>
                <span className="flex flex-col gap-0.5 pt-0.5">
                  <span className="text-base font-semibold text-text">{title}</span>
                  <span className="text-sm text-text-2 leading-relaxed">{body}</span>
                </span>
              </li>
            ))}
          </ol>
        </div>

        {/* ── Right: sign in ─────────────────────────────────────────────── */}
        <div className="w-full bg-surface border border-border-subtle rounded-xl shadow-md p-6 flex flex-col gap-5">
          <div className="flex flex-col gap-1">
            <h2 className="text-xl font-bold tracking-tight text-text">Sign in</h2>
            <p className="text-sm text-text-2">Use your Google account to continue.</p>
          </div>

          <Button
            id="google-signin-btn"
            variant="secondary"
            size="lg"
            block
            loading={isLoading}
            onClick={handleGoogleLogin}
          >
            {!isLoading && <GoogleIcon />}
            {isLoading ? 'Signing in…' : 'Continue with Google'}
          </Button>

          {error && <Alert tone="error">{error}</Alert>}

          <p className="text-xs text-text-3 leading-relaxed pt-4 border-t border-border-subtle">
            By continuing you agree to our{' '}
            <button onClick={() => setModal('terms')} className="text-text-2 underline underline-offset-2 hover:text-accent cursor-pointer">Terms of Service</button>
            {' '}and{' '}
            <button onClick={() => setModal('privacy')} className="text-text-2 underline underline-offset-2 hover:text-accent cursor-pointer">Privacy Policy</button>.
          </p>
        </div>
      </main>

      {/* ── Footer ───────────────────────────────────────────────────────── */}
      <footer className="w-full max-w-5xl mx-auto px-5 sm:px-8 py-6 border-t border-border-subtle flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-text-3">
        <span>© {new Date().getFullYear()} Cognira</span>
        <div className="flex items-center gap-5">
          <button onClick={() => setModal('privacy')} className="hover:text-text-2 cursor-pointer">Privacy</button>
          <button onClick={() => setModal('terms')} className="hover:text-text-2 cursor-pointer">Terms</button>
          <button onClick={() => setModal('support')} className="hover:text-text-2 cursor-pointer">Support</button>
        </div>
      </footer>

      {/* ── Dialog ───────────────────────────────────────────────────────── */}
      {modal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-text/40 backdrop-blur-sm"
          onClick={closeModal}
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="dialog-title"
            onClick={e => e.stopPropagation()}
            className="w-full max-w-xl max-h-[80vh] flex flex-col bg-surface border border-border-subtle rounded-xl shadow-lg overflow-hidden"
          >
            <div className="flex items-center justify-between gap-4 px-5 py-4 border-b border-border-subtle">
              <h3 id="dialog-title" className="text-lg font-bold tracking-tight text-text">
                {modal === 'terms' && 'Terms of Service'}
                {modal === 'privacy' && 'Privacy Policy'}
                {modal === 'support' && 'Support'}
              </h3>
              <button
                onClick={closeModal}
                aria-label="Close"
                className="p-1.5 rounded-sm text-text-3 hover:text-text hover:bg-surface-2 cursor-pointer transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="px-5 py-5 overflow-y-auto text-sm text-text-2 leading-relaxed flex flex-col gap-4">
              {modal === 'terms' && (
                <>
                  <p><strong className="text-text">Using Cognira.</strong> Cognira is provided for teaching and study. By signing in you agree to use it for that purpose.</p>
                  <p><strong className="text-text">Who can sign in.</strong> Access is limited to verified students, teaching staff and administrators of the institution.</p>
                  <p><strong className="text-text">Your account.</strong> Keep your sign-in details to yourself. Anything done from your account is treated as done by you. Tell us straight away if you think someone else has access.</p>
                  <p><strong className="text-text">Material you upload.</strong> Course material you upload stays yours. You give us permission to read and index it for the sole purpose of generating your questions.</p>
                  <p><strong className="text-text">Limits.</strong> Cognira drafts questions automatically and can get things wrong — that is why you review them before publishing. We can’t be held responsible for questions published without review.</p>
                </>
              )}
              {modal === 'privacy' && (
                <>
                  <p><strong className="text-text">What we collect.</strong> Your name, email address and profile picture from Google when you sign in, plus the material you upload and your activity in the app.</p>
                  <p><strong className="text-text">What we use it for.</strong> Confirming who you are, setting you up as a student or teacher, generating your questions, and showing your progress.</p>
                  <p><strong className="text-text">Who sees it.</strong> Nobody outside the platform. We don’t sell your data or share it with advertisers. It’s stored in an access-controlled database.</p>
                  <p><strong className="text-text">Deleting it.</strong> Ask support and we’ll remove your account and any material you’ve uploaded.</p>
                </>
              )}
              {modal === 'support' && (
                <>
                  <p>For sign-in trouble, a wrong role on your account, or anything that looks broken, get in touch and we’ll sort it out.</p>
                  <div className="flex flex-col gap-2 rounded-md border border-border-subtle bg-surface-2 p-4 text-sm">
                    <p><strong className="text-text">Email</strong> — <a href="mailto:support@cognira.app" className="text-accent hover:underline">support@cognira.app</a></p>
                    <p><strong className="text-text">Hours</strong> — Monday to Friday, 9:00 to 17:00</p>
                  </div>
                </>
              )}
            </div>

            <div className="px-5 py-4 border-t border-border-subtle flex justify-end">
              <Button onClick={closeModal}>Close</Button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
