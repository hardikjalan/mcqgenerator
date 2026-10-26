'use client'

import { useEffect, useState } from 'react'
import { apiRequest, errorMessage } from '@/lib/api'
import type { UserRole } from '@/types/database'
import { Card, CardHeader } from '@/components/ui/Card'
import { Button } from '@/components/ui/Button'
import { Alert } from '@/components/ui/Alert'
import { Field, FormInput } from '@/components/ui/form-fields'

type Person = { id: string; email: string; full_name: string | null; role: UserRole | null; suspended: boolean }
type Audit = { id: string; actor_id: string; action: string; target_id: string; created_at: string }

export function AdminWorkspace({ mode }: { mode: 'people' | 'audit' }) {
  const [people, setPeople] = useState<Person[]>([])
  const [events, setEvents] = useState<Audit[]>([])
  const [filter, setFilter] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [revision, setRevision] = useState(0)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    Promise.all([apiRequest<Person[]>('/admin/people'), apiRequest<Audit[]>('/admin/audit')])
      .then(([a, b]) => { setPeople(a); setEvents(b); setLoaded(true) })
      .catch(e => { setError(errorMessage(e)); setLoaded(true) })
  }, [revision])
  const update = async (person: Person, patch: { role?: UserRole; suspended?: boolean }) => {
    setBusy(person.id); setError('')
    try {
      const value = await apiRequest<Person>(`/admin/people/${person.id}`, { method: 'PATCH', body: JSON.stringify({ role: person.role ?? 'student', suspended: person.suspended, ...patch }) })
      setPeople(previous => previous.map(p => p.id === value.id ? value : p)); setRevision(n => n + 1)
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(null) }
  }
  return <div className="max-w-5xl mx-auto flex flex-col gap-5">
    {error && <Alert>{error}</Alert>}{!loaded && <p role="status">Loading administration…</p>}
    <div className="grid sm:grid-cols-3 gap-4">{[['Accounts', people.length], ['Teachers', people.filter(p => p.role === 'faculty').length], ['Suspended', people.filter(p => p.suspended).length]].map(([label, count]) => <Card key={label}><p className="text-sm text-text-3">{label}</p><p className="text-xl font-bold mt-2 tabular">{count}</p></Card>)}</div>
    {mode === 'people' ? <Card><CardHeader title="Account access" hint="Role changes and suspensions take effect on subsequent API requests." />
      <Field id="people-search" label="Search accounts"><FormInput id="people-search" placeholder="Name or email" value={filter} onChange={setFilter} /></Field>
      <div className="overflow-x-auto mt-4"><table className="w-full text-sm text-left"><thead><tr><th className="py-2">Account</th><th>Role</th><th>Access</th></tr></thead><tbody>{people.filter(p => `${p.full_name} ${p.email}`.toLowerCase().includes(filter.toLowerCase())).map(person => <tr key={person.id} className="border-t border-border-subtle">
        <td className="py-3 pr-3"><span className="font-semibold">{person.full_name || 'Unnamed account'}</span><span className="block text-xs text-text-3">{person.email}</span></td>
        <td className="pr-3"><select aria-label={`Role for ${person.email}`} value={person.role ?? ''} disabled={busy === person.id} onChange={e => update(person, { role: e.target.value as UserRole })} className="bg-surface border border-border-strong rounded-md p-2"><option value="" disabled>Not onboarded</option>{(['student', 'faculty', 'admin'] as const).map(role => <option key={role}>{role}</option>)}</select></td>
        <td><Button size="sm" variant={person.suspended ? 'secondary' : 'danger'} loading={busy === person.id} onClick={() => update(person, { suspended: !person.suspended })}>{person.suspended ? 'Restore access' : 'Suspend'}</Button></td>
      </tr>)}</tbody></table></div>
    </Card> : <Card><CardHeader title="Recent account and assessment activity" hint="The latest 100 recorded events." /><div className="overflow-x-auto"><table className="w-full text-sm text-left"><thead><tr><th className="py-2">Action</th><th>Account</th><th>Time</th></tr></thead><tbody>{events.map(event => <tr key={event.id} className="border-t border-border-subtle"><td className="py-3 pr-3">{event.action.replaceAll('_', ' ')}</td><td className="pr-3">{people.find(p => p.id === event.actor_id)?.email ?? event.actor_id}</td><td className="text-text-3">{new Date(event.created_at).toLocaleString()}</td></tr>)}</tbody></table>{loaded && !events.length && <p className="text-sm text-text-3 py-3">No recorded activity yet.</p>}</div></Card>}
  </div>
}
