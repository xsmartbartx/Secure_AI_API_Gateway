'use client'
import { useState } from 'react'
import { Button, Card, ErrorState, PageHeader, Skeleton } from '@/components/ui'
import { api } from '@/lib/api'
import { useSession } from '@/lib/session'
import { useApi } from '@/lib/use-fetch'

type Me = { org: { name: string; plan: string; retention_days: number }; member: { email: string; role: string } }

export default function Settings() {
  const { data: me, error, loading, reload } = useApi<Me>('/api/me')
  const session = useSession()
  const [confirm, setConfirm] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const isOwner = me?.member.role === 'owner'

  async function destroy(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null)
    try {
      await api('/api/org/delete', { method: 'POST', body: JSON.stringify({ confirm }) })
      session.signOut()
      window.location.href = '/'
    } catch (e: any) { setErr(e.message); setBusy(false) }
  }

  return <>
    <PageHeader title="Settings" description="Your organization and how Gateway handles its data." />
    {loading && <Card className="space-y-3 p-6"><Skeleton className="w-40" /><Skeleton className="w-72" /></Card>}
    {error && <Card><ErrorState message={error.message} onRetry={reload} /></Card>}
    {me && <div className="space-y-6">
      <Card className="p-6">
        <h2 className="font-semibold">Organization</h2>
        <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
          <div><dt className="text-text-muted">Name</dt><dd className="font-medium">{me.org.name}</dd></div>
          <div><dt className="text-text-muted">Plan</dt><dd className="font-medium capitalize">{me.org.plan}</dd></div>
          <div><dt className="text-text-muted">Your role</dt><dd className="font-medium capitalize">{me.member.role}</dd></div>
        </dl>
      </Card>
      <Card className="p-6">
        <h2 className="font-semibold">Data retention</h2>
        <p className="mt-2 max-w-prose text-text-muted">Request logs are kept for {me.org.retention_days} days on the {me.org.plan} plan, then deleted within a day. Prompt text is never stored. After deletion we keep daily counts per key and model (no content) so your usage history and monthly quota stay accurate.</p>
      </Card>
      <Card className="border-danger p-6">
        <h2 className="font-semibold text-danger">Delete organization</h2>
        <p className="mt-2 max-w-prose text-text-muted">Permanently deletes this organization's API keys, request logs, usage counts, and member records. Your subscription is cancelled first. Apps using your keys stop working immediately. This cannot be undone.</p>
        {isOwner ? <form onSubmit={destroy} className="mt-4 max-w-md space-y-3">
          <label htmlFor="confirm" className="block text-sm font-medium">Type <span className="font-mono">{me.org.name}</span> to confirm</label>
          <input id="confirm" autoComplete="off" value={confirm} onChange={e => setConfirm(e.target.value)} className="h-10 w-full rounded-md border border-border-input bg-bg px-3" />
          <Button type="submit" variant="danger" loading={busy} disabled={confirm !== me.org.name}>Delete organization</Button>
          {err && <p role="alert" className="text-sm text-danger">{err}</p>}
        </form> : <p className="mt-4 text-sm">Only an owner can delete the organization.</p>}
      </Card>
    </div>}
  </>
}
