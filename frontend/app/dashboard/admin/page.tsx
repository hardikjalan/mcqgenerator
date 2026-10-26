'use client'
import { useState } from 'react'
import { LayoutDashboard, Users, FileStack } from 'lucide-react'
import { AppShell, type NavItem } from '@/components/shared/AppShell'
import { AdminWorkspace } from '@/components/shared/AdminWorkspace'
import { AssessmentWorkspace } from '@/components/shared/AssessmentWorkspace'

export default function AdminDashboard() {
  const [mode, setMode] = useState<'people' | 'content' | 'audit'>('people')
  const nav: NavItem[] = [
    { label: 'People', Icon: Users, active: mode === 'people', onClick: () => setMode('people') },
    { label: 'Assessments', Icon: FileStack, active: mode === 'content', onClick: () => setMode('content') },
    { label: 'Activity', Icon: LayoutDashboard, active: mode === 'audit', onClick: () => setMode('audit') },
  ]
  return <AppShell nav={nav} roleLabel="Admin" title={mode === 'people' ? 'Account management' : mode === 'content' ? 'Assessments' : 'Activity log'}>
    {mode === 'content' ? <AssessmentWorkspace /> : <AdminWorkspace mode={mode} />}
  </AppShell>
}
