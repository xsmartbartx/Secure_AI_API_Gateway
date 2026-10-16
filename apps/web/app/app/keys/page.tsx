'use client'
import { useState } from 'react'
import { Button, Card, Empty, ErrorState, PageHeader, Skeleton, Td, Th } from '@/components/ui'
import { api, Key } from '@/lib/api'
import { useApi } from '@/lib/use-fetch'

export default function KeysPage() {
  const { data, error, loading, reload } = useApi<{ items: Key[] }>('/api/keys')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [secret, setSecret] = useState<string | null>(null)
  const [stored, setStored] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  async function create(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setMsg(null)
    try { const k = await api<Key & { secret: string }>('/api/keys', { method: 'POST', body: JSON.stringify({ name }) }); setSecret(k.secret); setStored(false); setName(''); reload() }
    catch (err: any) { setMsg(err.message) } finally { setBusy(false) }
  }
  async function revoke(k: Key) {
    if (!confirm(`Revoke "${k.name}"? Apps using it will stop working immediately.`)) return
    try { await api(`/api/keys/${k.id}/revoke`, { method: 'POST' }); reload() } catch (err: any) { setMsg(err.message) }
  }

  return <>
    <PageHeader title="API keys" description="Keys authenticate calls to /v1/chat. A secret is shown once, then stored only as a hash." />
    {secret && <div role="alert" className="mb-6 rounded-lg border border-warning bg-warning-subtle p-4">
      <p className="font-semibold text-warning">Copy your new key now. You won't see it again.</p>
      <code className="mt-2 block break-all rounded bg-bg p-3 font-mono text-[13px] text-text">{secret}</code>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button size="sm" variant="secondary" onClick={async () => { try { await navigator.clipboard?.writeText(secret) } catch { /* clipboard blocked */ } }}>Copy</Button>
        <label className="flex items-center gap-2 text-sm text-text"><input type="checkbox" checked={stored} onChange={e => setStored(e.target.checked)} /> I stored it somewhere safe</label>
        <Button size="sm" disabled={!stored} onClick={() => setSecret(null)}>Done</Button>
      </div></div>}
    <Card className="mb-6 p-4">
      <form onSubmit={create} className="flex flex-wrap items-end gap-3">
        <div className="min-w-60 flex-1"><label htmlFor="kn" className="mb-1 block text-sm font-medium">Key name</label>
          <input id="kn" required maxLength={80} value={name} onChange={e => setName(e.target.value)} placeholder="e.g. production-backend" className="h-10 w-full rounded-md border border-border-input bg-bg px-3" /></div>
        <Button type="submit" loading={busy}>Create key</Button>
      </form>
      {msg && <p role="alert" className="mt-2 text-sm text-danger">{msg}</p>}
    </Card>
    <Card className="overflow-x-auto">
      {loading && <div className="space-y-3 p-4">{[0, 1, 2].map(i => <Skeleton key={i} className="h-6" />)}</div>}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && data.items.length === 0 && <Empty title="No keys yet" help="Name your first key above to start calling Gateway." />}
      {data && data.items.length > 0 && <table className="w-full text-sm"><thead className="border-b border-border"><tr><Th>Name</Th><Th>Key</Th><Th>Limit</Th><Th>Last used</Th><Th>Status</Th><Th><span className="sr-only">Actions</span></Th></tr></thead>
        <tbody className="divide-y divide-border">{data.items.map(k => <tr key={k.id}>
          <Td className="max-w-48 truncate font-medium">{k.name}</Td><Td className="font-mono text-xs">{k.prefix}…{k.last4}</Td><Td>{k.rpm_limit}/min</Td>
          <Td className="text-text-muted">{k.last_used_at ? new Date(k.last_used_at).toLocaleString() : 'Never'}</Td>
          <Td>{k.revoked_at ? <span className="text-text-muted">Revoked</span> : <span className="text-success">Active</span>}</Td>
          <Td>{!k.revoked_at && <Button size="sm" variant="ghost" onClick={() => revoke(k)}>Revoke</Button>}</Td></tr>)}</tbody></table>}
    </Card>
  </>
}
