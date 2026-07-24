'use client'

import { BookOpen, CheckCircle2, TrendingUp } from 'lucide-react'
import { AppShell, type NavItem } from '@/components/shared/AppShell'
import { Card } from '@/components/ui/Card'

const NAV: NavItem[] = [
  { label: 'My quizzes', href: '/dashboard/student', Icon: BookOpen },
  { label: 'Completed',  Icon: CheckCircle2 },
  { label: 'Progress',   Icon: TrendingUp },
]

export default function StudentDashboard() {
  return (
    <AppShell nav={NAV} roleLabel="Student" title="My quizzes">
      <div className="max-w-3xl mx-auto">
        <Card className="flex flex-col items-center text-center gap-3 py-14">
          <span className="w-11 h-11 rounded-lg bg-accent-soft border border-accent-line text-accent flex items-center justify-center">
            <BookOpen className="w-5 h-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-text">No quizzes yet</h2>
          <p className="text-base text-text-2 max-w-sm">
            When a teacher publishes a quiz for your class it’ll appear here, with the
            deadline and how long you get to finish it.
          </p>
        </Card>
      </div>
    </AppShell>
  )
}
