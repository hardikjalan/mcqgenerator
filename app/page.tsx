'use client'

import { useState, useEffect, Suspense } from 'react'
import { useSearchParams } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'

// SVG Icons
const GoogleIcon = () => (
  <svg viewBox="0 0 24 24" width="20" height="20" className="flex-shrink-0">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z" fill="#FBBC05" />
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335" />
  </svg>
)

const LogoIcon = () => (
  <svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" strokeWidth="2" className="text-indigo-400">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const SparklesIcon = () => (
  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="2" className="text-indigo-400">
    <path d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364-6.364l-.707.707M6.343 17.657l-.707.707m0-12.728l.707.707m10.607 10.607l.707.707" strokeLinecap="round" />
  </svg>
)

// Platform Core Pillars
const pillars = [
  {
    title: 'Semantic RAG Engine',
    desc: 'Extracts and chunks learning resources (PDF, PPT, DOCX) to generate fully contextualized, grounded assessments.',
    badge: 'Content Grounded',
    color: 'border-indigo-500/20 text-indigo-400 bg-indigo-500/5'
  },
  {
    title: "Bloom's Taxonomy Alignment",
    desc: 'Generates and classifies questions across 6 cognitive levels, matching basic recall up to evaluation and creation.',
    badge: 'Cognitive Depth',
    color: 'border-purple-500/20 text-purple-400 bg-purple-500/5'
  },
  {
    title: 'Adaptive Assessment Paths',
    desc: "Dynamically shapes the quiz based on student accuracy, response speed, and topic mastery instead of static lists.",
    badge: 'Personalized',
    color: 'border-emerald-500/20 text-emerald-400 bg-emerald-500/5'
  },
  {
    title: 'Actionable Learning Analytics',
    desc: 'Detects weak concepts, suggests revision strategies, and creates automated feedback loops beyond exam scores.',
    badge: 'Mastery Insights',
    color: 'border-cyan-500/20 text-cyan-400 bg-cyan-500/5'
  }
]

// ── Error reader (must be wrapped in Suspense because of useSearchParams) ────
function ErrorFromUrl({ onError }: { onError: (msg: string) => void }) {
  const searchParams = useSearchParams()

  useEffect(() => {
    const urlError = searchParams.get('error')
    if (urlError === 'unauthorized_domain') {
      onError('Access restricted. Only @vitstudent.ac.in and @vit.ac.in email addresses are allowed.')
    } else if (urlError === 'auth_failed') {
      onError('Authentication failed. Please try again.')
    } else if (urlError === 'no_email') {
      onError('Could not retrieve your email. Please try a different Google account.')
    } else if (urlError === 'no_role') {
      onError('Your account role could not be determined. Contact support.')
    } else if (urlError === 'db_error') {
      onError('An error occurred while setting up your profile. Please try logging in again, or contact support if the issue persists.')
    }
  }, [searchParams, onError])

  return null
}

// ── Main Login Page ──────────────────────────────────────────────────────────
export default function LoginPage() {
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activePillar, setActivePillar] = useState(0)
  const [modalContent, setModalContent] = useState<'terms' | 'privacy' | 'support' | null>(null)

  // Auto-highlight active platform features
  useEffect(() => {
    const interval = setInterval(() => {
      setActivePillar((prev) => (prev + 1) % pillars.length)
    }, 3500)
    return () => clearInterval(interval)
  }, [])

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
      setError(err instanceof Error ? err.message : 'Authentication failed. Please try again.')
      setIsLoading(false)
    }
  }

  return (
    <div className="relative min-h-screen lg:h-screen lg:max-h-screen lg:overflow-hidden flex flex-col justify-between selection:bg-indigo-500/30 selection:text-white px-4 sm:px-6 lg:px-8">

      {/* Read ?error= from URL — inside Suspense per Next.js 16 requirement */}
      <Suspense fallback={null}>
        <ErrorFromUrl onError={setError} />
      </Suspense>

      {/* Background Orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
        <div className="absolute top-[-10%] left-[-10%] w-[50%] h-[50%] rounded-full bg-indigo-500/10 blur-[120px] animate-pulse-soft" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50%] h-[50%] rounded-full bg-cyan-500/10 blur-[120px] animate-pulse-soft" style={{ animationDelay: '2s' }} />
        <div className="absolute inset-0 opacity-[0.015]"
          style={{ backgroundImage: 'linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)', backgroundSize: '40px 40px' }} />
      </div>

      {/* Header */}
      <header className="relative z-10 w-full max-w-7xl mx-auto py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center shadow-lg shadow-indigo-500/5">
            <LogoIcon />
          </div>
          <div>
            <span className="text-xl font-bold tracking-tight text-white font-display">Cognira</span>
            <span className="block text-[10px] text-slate-500 font-semibold tracking-widest uppercase">Cognition & Intelligence</span>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <main className="relative z-10 flex-1 w-full max-w-7xl mx-auto grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-10 items-center py-6 lg:py-0">

        {/* Left: Branding & Platform Pillars */}
        <div className="lg:col-span-7 flex flex-col justify-center text-left space-y-5 lg:space-y-6 max-w-2xl mx-auto lg:mx-0">

          <div className="inline-flex items-center gap-2 self-start px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 border border-indigo-500/20 text-indigo-300">
            <SparklesIcon />
            <span>AI-Powered Adaptive Assessment Ecosystem</span>
          </div>

          <div className="space-y-3">
            <h1 className="text-3xl sm:text-4xl lg:text-4xl xl:text-5xl font-extrabold tracking-tight text-white font-display leading-[1.15]">
              Assess Smarter.{' '}
              <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-cyan-400 bg-clip-text text-transparent">
                Learn Deeper.
              </span>
            </h1>
            <p className="text-sm sm:text-base text-slate-400 max-w-xl leading-relaxed">
              Cognira transforms traditional static quizzes into personalized learning experiences.
              By understanding educational resources and learner performance, it creates intelligent, adaptive assessments.
            </p>
          </div>

          <div className="space-y-3">
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">Core Platform Architecture</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {pillars.map((p, idx) => (
                <div
                  key={p.title}
                  className={`p-3.5 rounded-xl border transition-all duration-300 text-left cursor-default ${idx === activePillar
                      ? `${p.color} shadow-lg shadow-indigo-500/5 scale-[1.015]`
                      : 'border-slate-800/60 bg-slate-900/10 text-slate-500'
                    }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <div className={`font-display font-bold text-xs tracking-tight ${idx === activePillar ? 'text-white' : 'text-slate-400'}`}>
                      {p.title}
                    </div>
                    {idx === activePillar && (
                      <span className="text-[9px] font-bold px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 uppercase tracking-wider">
                        {p.badge}
                      </span>
                    )}
                  </div>
                  <div className={`text-[11px] leading-relaxed ${idx === activePillar ? 'text-slate-300' : 'text-slate-500'}`}>
                    {p.desc}
                  </div>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* Right: Login Card */}
        <div className="lg:col-span-5 flex items-center justify-center w-full max-w-md mx-auto lg:mx-0">
          <div className="w-full relative rounded-3xl p-6 sm:p-8 glass-effect glass-effect-hover shadow-2xl shadow-black/80">

            <div className="flex flex-col items-center text-center mb-6">
              <div className="h-12 w-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/25 flex items-center justify-center shadow-inner mb-3">
                <LogoIcon />
              </div>
              <h2 className="text-xl font-bold text-white font-display tracking-tight mb-1">Sign in to Cognira</h2>
              <p className="text-[11px] text-slate-400">Only @vit.ac.in and @vitstudent.ac.in accounts are allowed</p>
            </div>

            <div className="space-y-5">
              <button
                id="google-signin-btn"
                onClick={handleGoogleLogin}
                disabled={isLoading}
                className="w-full flex items-center justify-center gap-3 h-12 rounded-xl cursor-pointer font-semibold text-white text-xs bg-slate-900 border border-slate-800 hover:bg-slate-850 hover:border-slate-700 active:scale-[0.98] transition-all duration-200 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {isLoading ? (
                  <span className="flex items-center gap-2 text-slate-400">
                    <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Signing in...
                  </span>
                ) : (
                  <>
                    <GoogleIcon />
                    <span>Continue with Google</span>
                  </>
                )}
              </button>

              {error && (
                <div className="p-3 rounded-xl border border-rose-500/20 bg-rose-500/10 text-[11px] text-rose-300 flex items-start gap-2">
                  <span className="text-xs flex-shrink-0">⚠️</span>
                  <span className="leading-normal">{error}</span>
                </div>
              )}
            </div>

            <div className="mt-6 pt-5 border-t border-slate-800/60 text-center">
              <p className="text-[10px] text-slate-500 leading-relaxed">
                By entering, you agree to our{' '}
                <button
                  onClick={() => setModalContent('terms')}
                  className="text-slate-400 hover:text-white underline underline-offset-2 transition-colors cursor-pointer bg-transparent border-0 p-0"
                >
                  Terms of Service
                </button>
                {' '}and{' '}
                <button
                  onClick={() => setModalContent('privacy')}
                  className="text-slate-400 hover:text-white underline underline-offset-2 transition-colors cursor-pointer bg-transparent border-0 p-0"
                >
                  Privacy Policy
                </button>.
              </p>
            </div>

          </div>
        </div>

      </main>

      {/* Footer */}
      <footer className="relative z-10 w-full max-w-7xl mx-auto py-4 border-t border-slate-900/60 flex flex-col sm:flex-row items-center justify-between gap-2 text-[10px] text-slate-500">
        <div>&copy; {new Date().getFullYear()} Cognira Platform. All rights reserved.</div>
        <div className="flex items-center gap-6">
          <button
            onClick={() => setModalContent('privacy')}
            className="hover:text-slate-350 transition-colors cursor-pointer bg-transparent border-0 p-0"
          >
            Privacy Policy
          </button>
          <button
            onClick={() => setModalContent('terms')}
            className="hover:text-slate-350 transition-colors cursor-pointer bg-transparent border-0 p-0"
          >
            Terms of Service
          </button>
          <button
            onClick={() => setModalContent('support')}
            className="hover:text-slate-350 transition-colors cursor-pointer bg-transparent border-0 p-0"
          >
            Contact Support
          </button>
        </div>
      </footer>

      {/* Modal Overlay */}
      {modalContent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
          <div className="relative w-full max-w-2xl max-h-[80vh] overflow-hidden rounded-3xl border border-slate-800 bg-slate-900/90 shadow-2xl flex flex-col">
            {/* Modal Header */}
            <div className="p-6 border-b border-slate-800 flex items-center justify-between">
              <h3 className="text-lg font-bold text-white font-display">
                {modalContent === 'terms' && 'Terms of Service'}
                {modalContent === 'privacy' && 'Privacy Policy'}
                {modalContent === 'support' && 'Contact Support'}
              </h3>
              <button
                onClick={() => setModalContent(null)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
                aria-label="Close modal"
              >
                <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {/* Modal Body */}
            <div className="p-6 overflow-y-auto flex-1 text-slate-300 text-xs sm:text-sm space-y-4 leading-relaxed">
              {modalContent === 'terms' && (
                <div className="space-y-4">
                  <p><strong>1. Acceptance of Terms</strong><br />Welcome to Cognira. By accessing or using our AI-powered Adaptive Assessment Ecosystem, you agree to comply with and be bound by these Terms of Service.</p>
                  <p><strong>2. Eligibility & Academic Use</strong><br />Access to Cognira is restricted to verified faculty, administrators, and students with active email addresses from VIT University (ending with <code>@vit.ac.in</code> or <code>@vitstudent.ac.in</code>). Registration or access using other email domains is strictly unauthorized.</p>
                  <p><strong>3. User Accounts & Security</strong><br />You are responsible for safeguarding your authentication credentials. Any activity performed under your account is your responsibility. Please notify us immediately of any unauthorized breach.</p>
                  <p><strong>4. Content Grounding & Uploads</strong><br />Users may upload course materials (such as lecture slides, PDFs, and documentation) for generating assessments. You retain ownership of uploaded content but grant the platform the necessary operational rights to parse, chunk, and index the text for RAG (Retrieval-Augmented Generation) services.</p>
                  <p><strong>5. Limitation of Liability</strong><br />Cognira is an educational tool provided &quot;as is&quot; without warranties of any kind. We are not responsible for database query latencies, network disconnects, or evaluation score discrepancies.</p>
                </div>
              )}

              {modalContent === 'privacy' && (
                <div className="space-y-4">
                  <p><strong>1. Information We Collect</strong><br />We collect Google identity metadata (name, email address, profile avatar) upon OAuth sign-in. We also store any course text materials uploaded and study logs generated during your usage of the ecosystem.</p>
                  <p><strong>2. Usage of Collected Information</strong><br />Your data is solely used to verify your academic domain status, set your system access role (Faculty, Student, or Admin), tailor adaptive assessment feedback loops, and compile personal progress statistics.</p>
                  <p><strong>3. Data Sharing & Privacy</strong><br />We do not share, sell, or disclose user data to external advertising services. All data is processed and stored securely inside authenticated databases hosted on Supabase.</p>
                  <p><strong>4. Data Retention</strong><br />We retain academic profiles as long as your university enrollment or employment remains active. You can request deletion of account details and uploaded materials by sending an inquiry to support.</p>
                </div>
              )}

              {modalContent === 'support' && (
                <div className="space-y-4">
                  <p>For account issues, role mapping updates, database connection issues, or domain authentication help, please reach out to our administration team:</p>
                  <div className="p-4 rounded-2xl bg-slate-950/40 border border-slate-800 space-y-2 text-xs">
                    <p><strong>Email Address:</strong> <a href="mailto:support@cognira.vit.ac.in" className="text-indigo-400 hover:underline">support@cognira.vit.ac.in</a></p>
                    <p><strong>Office Hours:</strong> Monday – Friday, 9:00 AM – 5:00 PM</p>
                    <p><strong>System Admin:</strong> Cognira Platform Development Group</p>
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-6 border-t border-slate-800 flex justify-end">
              <button
                onClick={() => setModalContent(null)}
                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 active:scale-[0.98] text-white font-semibold text-xs rounded-xl cursor-pointer transition-all duration-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
