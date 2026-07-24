'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase/client'
import type { OnboardingRole } from '@/types/database'

// ── Icons ─────────────────────────────────────────────────────────────────────
const LogoIcon = () => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" className="text-indigo-400">
    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const StudentIcon = () => (
  <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5">
    <path d="M12 14l9-5-9-5-9 5 9 5z" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M12 14l6.16-3.422a12.083 12.083 0 01.665 6.479A11.952 11.952 0 0012 20.055a11.952 11.952 0 00-6.824-2.998 12.078 12.078 0 01.665-6.479L12 14z" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M21 10v4" strokeLinecap="round" />
    <circle cx="21" cy="15" r="1" fill="currentColor" />
  </svg>
)

const TeacherIcon = () => (
  <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" strokeWidth="1.5">
    <rect x="3" y="3" width="18" height="14" rx="2" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M8 21h8M12 17v4" strokeLinecap="round" />
    <path d="M9 10l2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const CheckIcon = () => (
  <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.5">
    <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

const ArrowRightIcon = () => (
  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M5 12h14M12 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
)

// ── Page ──────────────────────────────────────────────────────────────────────
export default function OnboardingPage() {
  const router = useRouter()
  const [selected, setSelected] = useState<OnboardingRole | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [googleName, setGoogleName] = useState('')

  // Grab name from Google so we can store it via the RPC
  useEffect(() => {
    createClient().auth.getUser().then(({ data }) => {
      setGoogleName(data.user?.user_metadata?.full_name ?? '')
    })
  }, [])

  const handleConfirm = async () => {
    if (!selected || isSubmitting) return
    setIsSubmitting(true)
    setError(null)

    try {
      const supabase = createClient()
      const { error: rpcError } = await supabase.rpc('set_profile_role', {
        p_role: selected,
        p_full_name: googleName,
        p_institution: '',
      })
      if (rpcError) throw rpcError
      router.push(`/dashboard/${selected}`)
    } catch (err: any) {
      console.error('Role assignment failed:', err)
      setError(err?.message ?? 'Something went wrong. Please try again.')
      setIsSubmitting(false)
    }
  }

  return (
    <div className="relative min-h-screen flex flex-col items-center justify-center px-4 selection:bg-indigo-500/30 selection:text-white">

      {/* Background */}
      <div className="fixed inset-0 pointer-events-none z-0 overflow-hidden">
        <div className="absolute top-[-20%] left-[-10%] w-[60%] h-[60%] rounded-full bg-indigo-600/7 blur-[160px]" />
        <div className="absolute bottom-[-20%] right-[-10%] w-[55%] h-[55%] rounded-full bg-purple-500/5 blur-[140px]" />
        <div
          className="absolute inset-0 opacity-[0.013]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.15) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,0.15) 1px,transparent 1px)',
            backgroundSize: '44px 44px',
          }}
        />
      </div>

      <div className="relative z-10 w-full max-w-md">

        {/* Logo */}
        <div className="flex items-center gap-2.5 mb-12 justify-center">
          <div className="p-2 rounded-xl bg-slate-900 border border-slate-800">
            <LogoIcon />
          </div>
          <div>
            <span className="text-lg font-bold text-white tracking-tight">Cognira</span>
            <span className="block text-[9px] text-slate-600 uppercase tracking-widest font-semibold">Cognition & Intelligence</span>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-3xl p-8 glass-effect shadow-2xl shadow-black/60 border border-white/[0.06] space-y-7">

          <div className="text-center space-y-1.5">
            <h1 className="text-2xl font-extrabold text-white tracking-tight">Who are you?</h1>
            <p className="text-sm text-slate-500">Choose your role to get started. This can't be changed later.</p>
          </div>

          {/* Role cards */}
          <div className="grid grid-cols-2 gap-4">

            {/* Student */}
            <button
              id="role-student"
              onClick={() => setSelected('student')}
              disabled={isSubmitting}
              className={`group relative flex flex-col items-center gap-4 p-7 rounded-2xl border-2 text-center transition-all duration-200 cursor-pointer ${
                selected === 'student'
                  ? 'border-indigo-500 bg-indigo-500/10 shadow-[0_0_40px_rgba(99,102,241,0.14)]'
                  : 'border-slate-700/60 bg-slate-900/30 hover:border-indigo-500/40 hover:bg-indigo-500/5'
              }`}
            >
              <div className={`p-3 rounded-xl transition-colors duration-200 ${
                selected === 'student' ? 'bg-indigo-500/20 text-indigo-300' : 'bg-slate-800 text-slate-500 group-hover:text-indigo-400'
              }`}>
                <StudentIcon />
              </div>
              <div>
                <div className={`font-bold text-sm transition-colors ${selected === 'student' ? 'text-white' : 'text-slate-300'}`}>
                  Student
                </div>
                <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                  Learner at any level
                </div>
              </div>
              {selected === 'student' && (
                <div className="absolute top-3 right-3 w-5 h-5 rounded-full bg-indigo-500 flex items-center justify-center">
                  <CheckIcon />
                </div>
              )}
            </button>

            {/* Teacher */}
            <button
              id="role-teacher"
              onClick={() => setSelected('faculty')}
              disabled={isSubmitting}
              className={`group relative flex flex-col items-center gap-4 p-7 rounded-2xl border-2 text-center transition-all duration-200 cursor-pointer ${
                selected === 'faculty'
                  ? 'border-purple-500 bg-purple-500/10 shadow-[0_0_40px_rgba(139,92,246,0.14)]'
                  : 'border-slate-700/60 bg-slate-900/30 hover:border-purple-500/40 hover:bg-purple-500/5'
              }`}
            >
              <div className={`p-3 rounded-xl transition-colors duration-200 ${
                selected === 'faculty' ? 'bg-purple-500/20 text-purple-300' : 'bg-slate-800 text-slate-500 group-hover:text-purple-400'
              }`}>
                <TeacherIcon />
              </div>
              <div>
                <div className={`font-bold text-sm transition-colors ${selected === 'faculty' ? 'text-white' : 'text-slate-300'}`}>
                  Teacher
                </div>
                <div className="text-[11px] text-slate-500 mt-1 leading-relaxed">
                  Educator or instructor
                </div>
              </div>
              {selected === 'faculty' && (
                <div className="absolute top-3 right-3 w-5 h-5 rounded-full bg-purple-500 flex items-center justify-center">
                  <CheckIcon />
                </div>
              )}
            </button>
          </div>

          {/* Error */}
          {error && (
            <div className="p-3 rounded-xl border border-rose-500/20 bg-rose-500/8 text-[11px] text-rose-300 flex items-start gap-2">
              <span className="flex-shrink-0">⚠️</span>
              <span>{error}</span>
            </div>
          )}

          {/* Confirm button */}
          <button
            id="confirm-role"
            onClick={handleConfirm}
            disabled={!selected || isSubmitting}
            className={`w-full flex items-center justify-center gap-2 py-3.5 rounded-xl font-bold text-sm transition-all duration-200 cursor-pointer ${
              selected && !isSubmitting
                ? selected === 'faculty'
                  ? 'bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 text-white shadow-lg shadow-purple-900/30'
                  : 'btn-primary-glow text-white'
                : 'bg-slate-900/50 border border-slate-800 text-slate-600 cursor-not-allowed'
            }`}
          >
            {isSubmitting ? (
              <>
                <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                </svg>
                Setting up your workspace…
              </>
            ) : (
              <>
                {selected === 'faculty' ? 'Enter Teacher Dashboard' : selected === 'student' ? 'Enter Student Dashboard' : 'Select a role to continue'}
                {selected && <ArrowRightIcon />}
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
