'use client'
import { useState } from 'react'
import { Button, Card, ErrorState, PageHeader, Skeleton, Td, Th } from '@/components/ui'
import { api } from '@/lib/api'
import { useApi } from '@/lib/use-fetch'

type Role = 'owner' | 'admin' | 'developer' | 'viewer'
type Member = { id: string; email: string; role: Role; status: 'active' | 'suspended'; created_at: string; is_me: boolean }

const ROLE_HELP: Record<Role, string> = {
  owner: 'Everything, including deleting the organization and managing admins.',
  admin: 'Keys, providers, members (developers and viewers), billing.',
  developer: 'Create keys, use the playground, see logs and usage.',
  viewer: 'Read-only: logs, usage and members.',
}

export default function Team() {
  const { data, error, loading, reload } = useApi<{ items: Member[] }>('/api/members')
  const me = data?.items.find(m => m.is_me)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  // Mirrors the server rules (the server is what enforces them): owners manage everyone, admins only developers and viewers.
  const canManage = (m: Member) => !m.is_me && (me?.role === 'owner' || (me?.role === 'admin' && (m.role === 'developer' || m.role === 'viewer')))
  const roleChoices: Role[] = me?.role === 'owner' ? ['owner', 'admin', 'developer', 'viewer'] : ['developer', 'viewer']

  async function change(m: Member, body: { role?: Role; status?: 'active' | 'suspended' }) {
    setBusy(m.id); setMsg(null)
    try { await api(`/api/members/${m.id}`, { method: 'PATCH', body: JSON.stringify(body) }); reload() }
    catch (e: any) { setMsg(e.message) } finally { setBusy(null) }
  }
  function suspend(m: Member) {
    if (confirm(`Suspend ${m.email}? They lose access to this organization in Gateway right away. You can restore them later.`)) change(m, { status: 'suspended' })
  }

  return <>
    <PageHeader title="Team" description="Who can do what in this organization." />
    {msg && <p role="alert" className="mb-4 text-sm text-danger">{msg}</p>}
    <Card className="overflow-x-auto">
      {loading && <div className="space-y-3 p-4">{[0, 1, 2].map(i => <Skeleton key={i} className="h-6" />)}</div>}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && <table className="w-full text-sm">
        <thead className="border-b border-border"><tr><Th>Member</Th><Th>Role</Th><Th>Access</Th><Th>Joined</Th><Th><span className="sr-only">Actions</span></Th></tr></thead>
        <tbody className="divide-y divide-border">{data.items.map(m => <tr key={m.id}>
          <Td className="max-w-64 truncate font-medium">{m.email}{m.is_me && <span className="ml-2 rounded bg-surface px-1.5 py-0.5 text-xs font-normal text-text-muted">You</span>}</Td>
          <Td>{canManage(m)
            ? <><label htmlFor={`role-${m.id}`} className="sr-only">Role for {m.email}</label>
              <select id={`role-${m.id}`} value={m.role} disabled={busy === m.id} onChange={e => change(m, { role: e.target.value as Role })} className="h-9 rounded-md border border-border-input bg-bg px-2 capitalize">
                {[...new Set<Role>([...roleChoices, m.role])].map(r => <option key={r} value={r} disabled={!roleChoices.includes(r)}>{r}</option>)}</select></>
            : <span className="capitalize">{m.role}</span>}</Td>
          <Td>{m.status === 'active' ? <span className="text-success">Active</span> : <span className="font-medium text-danger">Suspended</span>}</Td>
          <Td className="whitespace-nowrap text-text-muted">{new Date(m.created_at).toLocaleDateString()}</Td>
          <Td>{canManage(m) && (m.status === 'active'
            ? <Button size="sm" variant="ghost" loading={busy === m.id} onClick={() => suspend(m)}>Suspend</Button>
            : <Button size="sm" variant="secondary" loading={busy === m.id} onClick={() => change(m, { status: 'active' })}>Restore</Button>)}</Td>
        </tr>)}</tbody></table>}
    </Card>

    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      <Card className="p-6">
        <h2 className="font-semibold">Adding people</h2>
        <p className="mt-2 text-text-muted">Invite teammates to your organization from your NEXORA account. They appear here the first time they open Gateway, with a role based on their account role that an owner can change.</p>
        <a href="https://account.onenexora.com" className="mt-3 inline-block text-sm font-semibold text-accent">Open NEXORA account →</a>
      </Card>
      <Card className="p-6">
        <h2 className="font-semibold">Roles</h2>
        <dl className="mt-2 space-y-2 text-sm">{(Object.keys(ROLE_HELP) as Role[]).map(r => <div key={r}><dt className="font-medium capitalize">{r}</dt><dd className="text-text-muted">{ROLE_HELP[r]}</dd></div>)}</dl>
        <p className="mt-3 text-xs text-text-muted">Suspending someone stops their access to Gateway but does not revoke the organization's API keys. If you think a key was exposed, rotate it on the API keys page.</p>
      </Card>
    </div>
  </>
}
