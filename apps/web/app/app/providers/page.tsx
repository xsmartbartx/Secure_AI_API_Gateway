'use client'
import { AlertTriangle, Check, CircleDashed } from 'lucide-react'
import { useState } from 'react'
import { Button, Card, Empty, ErrorState, PageHeader, Skeleton } from '@/components/ui'
import { api } from '@/lib/api'
import { useApi } from '@/lib/use-fetch'

type Conn = { id: string; provider: 'anthropic' | 'openai'; label: string; hint: string; is_default: boolean; status: 'ok' | 'failing' | 'untested'; created_at: string }
const NAMES = { anthropic: 'Anthropic', openai: 'OpenAI' } as const

function Status({ s }: Readonly<{ s: Conn['status'] }>) {
  const m = { ok: ['bg-success-subtle text-success', Check, 'Working'], failing: ['bg-danger-subtle text-danger', AlertTriangle, 'Failing'], untested: ['bg-surface text-text-muted', CircleDashed, 'Not tested'] } as const
  const [c, Icon, label] = m[s]
  return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${c}`}><Icon size={12} aria-hidden />{label}</span>
}

export default function Providers() {
  const { data, error, loading, reload } = useApi<{ items: Conn[] }>('/api/providers')
  const me = useApi<{ member: { role: string } }>('/api/me')
  const canEdit = me.data?.member.role === 'admin' || me.data?.member.role === 'owner'
  const [provider, setProvider] = useState<'anthropic' | 'openai'>('anthropic')
  const [label, setLabel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [busy, setBusy] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)

  async function add(e: React.FormEvent) {
    e.preventDefault(); setBusy('add'); setMsg(null)
    try {
      await api('/api/providers', { method: 'POST', body: JSON.stringify({ provider, label, api_key: apiKey }) })
      setLabel(''); reload()
    } catch (err: any) { setMsg(err.message) } finally { setApiKey(''); setBusy(null) } // the key leaves the page state either way
  }
  async function act(id: string, path: string, method = 'POST') {
    setBusy(id + path); setMsg(null)
    try { await api(`/api/providers/${id}${path}`, { method }); reload() } catch (err: any) { setMsg(err.message) } finally { setBusy(null) }
  }
  async function remove(c: Conn) {
    if (confirm(`Remove "${c.label}"? Calls will fall back to the next key, or to the shared provider.`)) await act(c.id, '', 'DELETE')
  }

  return <>
    <PageHeader title="Providers" description="Use your own model-provider API key. Calls use your default key; with none, Gateway uses the shared provider NEXORA configures." />
    {msg && <p role="alert" className="mb-4 text-sm text-danger">{msg}</p>}

    {canEdit && <Card className="mb-6 p-4">
      <h2 className="mb-3 font-semibold">Add a key</h2>
      <form onSubmit={add} className="flex flex-wrap items-end gap-3">
        <div><label htmlFor="prov" className="mb-1 block text-sm font-medium">Provider</label>
          <select id="prov" value={provider} onChange={e => setProvider(e.target.value as 'anthropic' | 'openai')} className="h-10 rounded-md border border-border-input bg-bg px-3">
            <option value="anthropic">Anthropic</option><option value="openai">OpenAI</option></select></div>
        <div className="min-w-40 flex-1"><label htmlFor="plabel" className="mb-1 block text-sm font-medium">Name</label>
          <input id="plabel" required maxLength={60} value={label} onChange={e => setLabel(e.target.value)} placeholder="e.g. production" className="h-10 w-full rounded-md border border-border-input bg-bg px-3" /></div>
        <div className="min-w-60 flex-2"><label htmlFor="pkey" className="mb-1 block text-sm font-medium">API key</label>
          <input id="pkey" required type="password" autoComplete="off" spellCheck={false} minLength={12} maxLength={400} value={apiKey} onChange={e => setApiKey(e.target.value)} className="h-10 w-full rounded-md border border-border-input bg-bg px-3 font-mono" /></div>
        <Button type="submit" loading={busy === 'add'}>Verify and save</Button>
      </form>
      <p className="mt-3 text-xs text-text-muted">We check the key with the provider before saving it. It is encrypted at rest and never shown again, only its last four characters.</p>
    </Card>}
    {!canEdit && me.data && <p className="mb-4 text-sm text-text-muted">Only admins and owners can add or remove keys.</p>}

    <Card className="overflow-x-auto">
      {loading && <div className="space-y-3 p-4">{[0, 1].map(i => <Skeleton key={i} className="h-6" />)}</div>}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data?.items.length === 0 && <Empty title="No provider keys yet" help="Until you add one, calls go through the shared provider NEXORA configures." />}
      {data && data.items.length > 0 && <ul className="divide-y divide-border">{data.items.map(c => <li key={c.id} className="flex flex-wrap items-center gap-x-6 gap-y-2 p-4">
        <div className="min-w-48 flex-1"><p className="font-medium">{c.label}{c.is_default && <span className="ml-2 rounded bg-accent-subtle px-1.5 py-0.5 text-xs font-medium text-accent">Default</span>}</p>
          <p className="text-sm text-text-muted">{NAMES[c.provider]} · <span className="font-mono">{c.hint}</span></p></div>
        <Status s={c.status} />
        {canEdit && <div className="flex gap-2">
          <Button size="sm" variant="secondary" loading={busy === c.id + '/test'} onClick={() => act(c.id, '/test')}>Test</Button>
          {!c.is_default && <Button size="sm" variant="secondary" loading={busy === c.id + '/default'} onClick={() => act(c.id, '/default')}>Make default</Button>}
          <Button size="sm" variant="ghost" onClick={() => remove(c)}>Remove</Button>
        </div>}
      </li>)}</ul>}
    </Card>
  </>
}
