'use client'

import { LayoutDashboard, Users, FileStack } from 'lucide-react'
import { AppShell, type NavItem } from '@/components/shared/AppShell'
import { Card } from '@/components/ui/Card'

const NAV: NavItem[] = [
  { label: 'Overview', href: '/dashboard/admin', Icon: LayoutDashboard },
  { label: 'People',   Icon: Users },
  { label: 'Content',  Icon: FileStack },
]

export default function AdminDashboard() {
  return (
    <AppShell nav={NAV} roleLabel="Admin" title="Overview">
      <div className="max-w-3xl mx-auto">
        <Card className="flex flex-col items-center text-center gap-3 py-14">
          <span className="w-11 h-11 rounded-lg bg-accent-soft border border-accent-line text-accent flex items-center justify-center">
            <LayoutDashboard className="w-5 h-5" aria-hidden="true" />
          </span>
          <h2 className="text-lg font-bold text-text">Nothing to show yet</h2>
          <p className="text-base text-text-2 max-w-sm">
            Managing people and reviewing published content will live here.
          </p>
        </Card>
      </div>
    </AppShell>
  )
}
