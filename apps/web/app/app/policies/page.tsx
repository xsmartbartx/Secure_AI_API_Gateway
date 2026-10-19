'use client'
import { useEffect, useState } from 'react'
import { Button, Card, ErrorState, PageHeader, Skeleton } from '@/components/ui'
import { api } from '@/lib/api'
import { useApi } from '@/lib/use-fetch'

type Mode = 'off' | 'monitor' | 'enforce'
type ModelPolicy = { mode: Mode; models: string[]; version: number }

const MODES: { value: Mode; label: string; help: string }[] = [
  { value: 'off', label: 'Off', help: 'Any model can be called.' },
  { value: 'monitor', label: 'Monitor', help: 'Every call goes through. Calls to models not on the list are flagged in Logs and Security, so you can see what would be blocked.' },
  { value: 'enforce', label: 'Enforce', help: 'Calls to models not on the list are rejected before they reach the provider. They are logged as blocked and do not use your quota.' },
]

export default function Policies() {
  const { data, error, loading, reload } = useApi<{ model_allow: ModelPolicy }>('/api/policies')
  const me = useApi<{ member: { role: string } }>('/api/me')
  const canEdit = me.data?.member.role === 'admin' || me.data?.member.role === 'owner'
  const [mode, setMode] = useState<Mode>('off')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [probe, setProbe] = useState('')
  const [probeResult, setProbeResult] = useState<string | null>(null)

  useEffect(() => { if (data) { setMode(data.model_allow.mode); setText(data.model_allow.models.join('\n')) } }, [data])
  const saved = data?.model_allow
  const dirty = !!saved && (mode !== saved.mode || text.split('\n').map(l => l.trim()).filter(Boolean).join('\n') !== saved.models.join('\n'))

  async function save(e: React.FormEvent) {
    e.preventDefault(); setMsg(null)
    if (mode === 'enforce' && saved?.mode !== 'enforce' && !confirm('Turn on enforcement? Calls to any model not on the list are rejected immediately, including from the playground.')) return
    setBusy(true)
    try {
      const r = await api<ModelPolicy>('/api/policies/model_allow', { method: 'PUT', body: JSON.stringify({ mode, models: text.split('\n') }) })
      setMsg({ ok: true, text: `Saved (version ${r.version}).` }); setProbeResult(null); reload()
    } catch (err: any) { setMsg({ ok: false, text: err.message }) } finally { setBusy(false) }
  }
  async function check(e: React.FormEvent) {
    e.preventDefault(); setProbeResult(null)
    try {
      const r = await api<{ allowed: boolean; matched: string | null; mode: Mode; flagged: boolean }>('/api/policies/model_allow/test', { method: 'POST', body: JSON.stringify({ model: probe }) })
      if (r.mode === 'off') setProbeResult('Allowed: the policy is off.')
      else if (r.matched) setProbeResult(`Allowed: matches “${r.matched}”.`)
      else setProbeResult(r.flagged ? 'Would be flagged: not on the list (monitor mode lets it through).' : 'Blocked: not on the list.')
    } catch (err: any) { setProbeResult(err.message) }
  }

  return <>
    <PageHeader title="Policies" description="Rules applied to every call before it is sent to a provider." />
    {loading && <Card className="space-y-3 p-6"><Skeleton className="w-48" /><Skeleton className="h-24 w-full" /></Card>}
    {error && <Card><ErrorState message={error.message} onRetry={reload} /></Card>}
    {saved && <div className="space-y-6">
      <Card className="p-6">
        <h2 className="font-semibold">Allowed models</h2>
        <p className="mt-1 max-w-prose text-text-muted">Limit which models your keys can use, for example to keep calls on approved models. The model a call asks for, or the default if it names none, is checked against this list.</p>
        <form onSubmit={save} className="mt-4 space-y-5">
          <fieldset disabled={!canEdit} className="space-y-2">
            <legend className="mb-1 text-sm font-medium">Mode</legend>
            {MODES.map(m => <label key={m.value} className="flex cursor-pointer items-start gap-3 rounded-md border border-border p-3 has-[:checked]:border-accent has-[:checked]:bg-accent-subtle">
              <input type="radio" name="mode" value={m.value} checked={mode === m.value} onChange={() => setMode(m.value)} className="mt-1" />
              <span><span className="block font-medium">{m.label}</span><span className="block text-sm text-text-muted">{m.help}</span></span></label>)}
          </fieldset>
          <div>
            <label htmlFor="models" className="mb-1 block text-sm font-medium">Models on the list</label>
            <textarea id="models" rows={6} readOnly={!canEdit} spellCheck={false} value={text} onChange={e => setText(e.target.value)} placeholder={'claude-*\ngpt-4o'} className="w-full rounded-md border border-border-input bg-bg p-3 font-mono text-sm" />
            <p className="mt-1 text-xs text-text-muted">One per line. <span className="font-mono">*</span> matches any characters and <span className="font-mono">?</span> one character. Not case sensitive. Up to 50 entries. <span className="font-mono">gpt-4o</span> matches only that model, not <span className="font-mono">gpt-4o-mini</span>.</p>
          </div>
          {canEdit
            ? <div className="flex flex-wrap items-center gap-3"><Button type="submit" loading={busy} disabled={!dirty}>Save policy</Button>
              {msg && <p role={msg.ok ? 'status' : 'alert'} className={`text-sm ${msg.ok ? 'text-success' : 'text-danger'}`}>{msg.text}</p>}</div>
            : <p className="text-sm text-text-muted">Only admins and owners can change policies.</p>}
        </form>
      </Card>

      {canEdit && <Card className="p-6">
        <h2 className="font-semibold">Try a model name</h2>
        <p className="mt-1 text-sm text-text-muted">Checks a name against the saved policy. Nothing is sent to a provider.</p>
        <form onSubmit={check} className="mt-3 flex flex-wrap items-end gap-3">
          <div className="min-w-60 flex-1"><label htmlFor="probe" className="mb-1 block text-sm font-medium">Model</label>
            <input id="probe" required maxLength={200} value={probe} onChange={e => setProbe(e.target.value)} placeholder="e.g. claude-sonnet-5-5" className="h-10 w-full rounded-md border border-border-input bg-bg px-3 font-mono" /></div>
          <Button type="submit" variant="secondary">Check</Button>
        </form>
        {probeResult && <p role="status" className="mt-3 text-sm">{probeResult}</p>}
      </Card>}

      <Card className="p-6">
        <h2 className="font-semibold">Where blocked calls show up</h2>
        <p className="mt-1 max-w-prose text-sm text-text-muted">Blocked and flagged calls appear in Logs (filter by decision) and in Security events, and count in the Overview. Other policies, such as data loss prevention and prompt-injection detection, are on the roadmap.</p>
      </Card>
    </div>}
  </>
}
