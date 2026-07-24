'use client'

import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase/client'

export default function AdminDashboard() {
  const [user, setUser] = useState<{ name: string; email: string; avatar: string } | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getUser().then(({ data }) => {
      if (data.user) {
        setUser({
          name: data.user.user_metadata?.full_name ?? 'Admin',
          email: data.user.email ?? '',
          avatar: data.user.user_metadata?.avatar_url ?? '',
        })
      }
    })
  }, [])

  const handleSignOut = async () => {
    const supabase = createClient()
    await supabase.auth.signOut()
    window.location.href = '/'
  }

  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 px-4">
      <div className="text-center space-y-2">
        {user?.avatar && (
          <img src={user.avatar} alt={user.name} className="w-16 h-16 rounded-full mx-auto ring-2 ring-violet-500/40" />
        )}
        <h1 className="text-2xl font-bold text-white font-display">Welcome, {user?.name ?? '...'}</h1>
        <p className="text-sm text-slate-400">{user?.email}</p>
        <span className="inline-block px-3 py-1 text-xs font-semibold rounded-full bg-violet-500/15 border border-violet-500/30 text-violet-400">
          Admin
        </span>
      </div>

      <div className="glass-effect rounded-2xl p-6 max-w-md w-full text-center space-y-2">
        <p className="text-slate-300 text-sm">🚧 Admin Command Center is being built.</p>
        <p className="text-slate-500 text-xs">System configuration, logs, role updates, and user analytics will appear here.</p>
      </div>

      <button
        onClick={handleSignOut}
        className="text-xs text-slate-500 hover:text-rose-400 transition-colors underline underline-offset-2"
      >
        Sign out
      </button>
    </div>
  )
}
