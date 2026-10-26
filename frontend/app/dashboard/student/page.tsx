'use client'
import { useState } from 'react'
import { BookOpen, CheckCircle2, TrendingUp } from 'lucide-react'
import { AppShell, type NavItem } from '@/components/shared/AppShell'
import { StudentWorkspace } from '@/components/student/StudentWorkspace'

export default function StudentDashboard() {
  const [mode, setMode] = useState<'quizzes' | 'completed' | 'progress'>('quizzes')
  const nav: NavItem[] = [
    { label: 'My quizzes', Icon: BookOpen, active: mode === 'quizzes', onClick: () => setMode('quizzes') },
    { label: 'Completed', Icon: CheckCircle2, active: mode === 'completed', onClick: () => setMode('completed') },
    { label: 'Progress', Icon: TrendingUp, active: mode === 'progress', onClick: () => setMode('progress') },
  ]
  return <AppShell nav={nav} roleLabel="Student" title={mode === 'quizzes' ? 'My quizzes' : mode === 'completed' ? 'Completed assessments' : 'Learning progress'}><StudentWorkspace mode={mode} /></AppShell>
}
