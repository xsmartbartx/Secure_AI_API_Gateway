'use client'
import { useState } from 'react'
import { Button } from '@/components/ui'
import { api, Key } from '@/lib/api'

const toNumber = (v: string) => (v.trim() === '' ? null : Number(v))

/** Edit a key's monthly caps. Blank means no cap beyond the organization's quota. */
export function LimitsEditor({ k, onDone }: Readonly<{ k: Key; onDone: (changed: boolean) => void }>) {
  const [calls, setCalls] = useState(k.monthly_call_limit?.toString() ?? '')
  const [tokens, setTokens] = useState(k.monthly_token_limit?.toString() ?? '')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function save(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null)
    try { await api(`/api/keys/${k.id}`, { method: 'PATCH', body: JSON.stringify({ monthly_call_limit: toNumber(calls), monthly_token_limit: toNumber(tokens) }) }); onDone(true) }
    catch (error: any) { setErr(error.message); setBusy(false) }
  }

  return <form onSubmit={save} className="flex flex-wrap items-end gap-3 bg-surface p-4" aria-label={`Monthly limits for ${k.name}`}>
    <div><label htmlFor={`cl-${k.id}`} className="mb-1 block text-xs font-medium">Calls per month</label>
      <input id={`cl-${k.id}`} type="number" min={1} max={1000000000} value={calls} onChange={e => setCalls(e.target.value)} placeholder="No limit" className="h-9 w-36 rounded-md border border-border-input bg-bg px-2" /></div>
    <div><label htmlFor={`tl-${k.id}`} className="mb-1 block text-xs font-medium">Tokens per month</label>
      <input id={`tl-${k.id}`} type="number" min={1} max={1000000000} value={tokens} onChange={e => setTokens(e.target.value)} placeholder="No limit" className="h-9 w-36 rounded-md border border-border-input bg-bg px-2" /></div>
    <Button type="submit" size="sm" loading={busy}>Save limits</Button>
    <Button type="button" size="sm" variant="ghost" onClick={() => onDone(false)}>Cancel</Button>
    <p className="w-full text-xs text-text-muted">When a key reaches a limit, its calls get a 429 until the month resets (UTC). Token limits are checked before each call, so one call can run a little past the limit. Blocked and failed calls do not count.</p>
    {err && <p role="alert" className="w-full text-sm text-danger">{err}</p>}
  </form>
}
