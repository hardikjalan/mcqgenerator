'use client'

import { useState } from 'react'
import { ArrowRight, Check, GraduationCap, Presentation } from 'lucide-react'
import { createClient } from '@/lib/supabase/client'
import { completeOnboarding } from '@/lib/onboarding'
import type { OnboardingRole } from '@/types/database'
import { Wordmark } from '@/components/ui/Logo'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'

const ROLES: { key: OnboardingRole; label: string; blurb: string; Icon: typeof GraduationCap }[] = [
  { key: 'student', label: 'Student', blurb: 'Take quizzes set for you', Icon: GraduationCap },
  { key: 'faculty', label: 'Teacher', blurb: 'Create and publish quizzes', Icon: Presentation },
]

export default function OnboardingPage() {
  const [selected, setSelected] = useState<OnboardingRole | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [dashboardPath, setDashboardPath] = useState<string | null>(null)

  const handleConfirm = async () => {
    if (!selected || isSubmitting) return
    if (dashboardPath) {
      window.location.replace(dashboardPath)
      return
    }
    setIsSubmitting(true)
    setError(null)

    try {
      const supabase = createClient()
      // Returns the role that ended up stored. Checking it matters: the old
      // version returned nothing, so a save that matched zero rows looked
      // identical to a real one — and the proxy then bounced the user
      // straight back here, with nothing on screen to explain why.
      const savedRole = await completeOnboarding(signal => supabase.rpc('set_profile_role', {
        p_role: selected,
        // The RPC reads the Google name from auth.users when this is empty.
        p_full_name: '',
        p_institution: '',
      }).abortSignal(signal))

      // Follow the stored role rather than the clicked one — if a role was
      // already set, that's where the proxy will send us anyway.
      const path = `/dashboard/${savedRole}`
      setDashboardPath(path)
      // A fresh request makes the proxy read the newly stored database role.
      window.location.replace(path)
    } catch (err: unknown) {
      console.error('Role assignment failed:', err)
      setError(err instanceof Error ? err.message : 'That didn’t save. Please try again.')
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-5 py-12">
      <div className="w-full max-w-md flex flex-col gap-8">

        <Wordmark size={32} className="self-center" />

        <div className="bg-surface border border-border-subtle rounded-xl shadow-md p-6 sm:p-7 flex flex-col gap-6">

          <div className="flex flex-col gap-1.5">
            <h1 className="text-2xl font-extrabold tracking-tight text-text">
              How will you use Cognira?
            </h1>
            <p className="text-sm text-text-2">
              Choose how you will use Cognira. An administrator can help if your role needs to change later.
            </p>
          </div>

          <div
            role="radiogroup"
            aria-label="Choose your role"
            className="grid grid-cols-2 gap-3"
          >
            {ROLES.map(({ key, label, blurb, Icon }) => {
              const active = selected === key
              return (
                <button
                  key={key}
                  id={`role-${key}`}
                  role="radio"
                  aria-checked={active}
                  onClick={() => setSelected(key)}
                  disabled={isSubmitting || dashboardPath !== null}
                  className={[
                    'group relative flex flex-col items-start gap-3 p-4 rounded-lg border text-left',
                    'transition-colors duration-150 cursor-pointer disabled:opacity-50',
                    active
                      ? 'border-accent bg-accent-soft'
                      : 'border-border-strong bg-surface hover:border-text-3 hover:bg-surface-2',
                  ].join(' ')}
                >
                  <span
                    className={[
                      'w-9 h-9 rounded-md flex items-center justify-center transition-colors',
                      active ? 'bg-accent text-on-accent' : 'bg-surface-2 text-text-3 group-hover:text-text-2',
                    ].join(' ')}
                  >
                    <Icon className="w-4.5 h-4.5" aria-hidden="true" />
                  </span>

                  <span className="flex flex-col gap-0.5">
                    <span className={`text-base font-bold ${active ? 'text-accent' : 'text-text'}`}>
                      {label}
                    </span>
                    <span className="text-xs text-text-2 leading-snug">{blurb}</span>
                  </span>

                  {active && (
                    <span className="absolute top-3 right-3 w-4 h-4 rounded-full bg-accent text-on-accent flex items-center justify-center">
                      <Check className="w-2.5 h-2.5" strokeWidth={3.5} aria-hidden="true" />
                    </span>
                  )}
                </button>
              )
            })}
          </div>

          {error && <Alert tone="error">{error}</Alert>}
          {dashboardPath && <Alert tone="success">Your account is ready. <a className="underline" href={dashboardPath}>Open your dashboard</a>.</Alert>}

          <Button
            id="confirm-role"
            block
            size="lg"
            disabled={!selected}
            loading={isSubmitting}
            onClick={handleConfirm}
          >
            {isSubmitting
              ? 'Setting up your account…'
              : dashboardPath
              ? 'Open dashboard'
              : selected
              ? `Continue as ${selected === 'faculty' ? 'a teacher' : 'a student'}`
              : 'Pick one to continue'}
            {selected && !isSubmitting && <ArrowRight className="w-4 h-4" aria-hidden="true" />}
          </Button>
        </div>
      </div>
    </div>
  )
}
