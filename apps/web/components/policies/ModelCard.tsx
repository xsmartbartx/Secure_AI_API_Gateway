'use client'
import { useEffect, useState } from 'react'
import { Button, Card } from '@/components/ui'
import { api } from '@/lib/api'
import { Mode, ModeFieldset, SaveRow } from './shared'

export type ModelPolicy = { mode: Mode; models: string[]; version: number }

const OPTIONS = [
  { value: 'off' as const, label: 'Off', help: 'Any model can be called.' },
  { value: 'monitor' as const, label: 'Monitor', help: 'Every call goes through. Calls to models not on the list are flagged in Logs and Security, so you can see what would be blocked.' },
  { value: 'enforce' as const, label: 'Enforce', help: 'Calls to models not on the list are rejected before they reach the provider. They are logged as blocked and do not use your quota.' },
]

const tidy = (text: string) => text.split('\n').map(l => l.trim()).filter(Boolean).join('\n')

export function ModelCard({ policy, canEdit, onSaved }: Readonly<{ policy: ModelPolicy; canEdit: boolean; onSaved: () => void }>) {
  const [mode, setMode] = useState<Mode>(policy.mode)
  const [text, setText] = useState(policy.models.join('\n'))
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [probe, setProbe] = useState('')
  const [probeResult, setProbeResult] = useState<string | null>(null)
  useEffect(() => { setMode(policy.mode); setText(policy.models.join('\n')) }, [policy])
  const dirty = mode !== policy.mode || tidy(text) !== policy.models.join('\n')

  async function save(e: React.FormEvent) {
    e.preventDefault(); setMsg(null)
    if (mode === 'enforce' && policy.mode !== 'enforce' && !confirm('Turn on enforcement? Calls to any model not on the list are rejected immediately, including from the playground.')) return
    setBusy(true)
    try {
      const r = await api<ModelPolicy>('/api/policies/model_allow', { method: 'PUT', body: JSON.stringify({ mode, models: text.split('\n') }) })
      setMsg({ ok: true, text: `Saved (version ${r.version}).` }); setProbeResult(null); onSaved()
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

  return <section aria-labelledby="policy-model-h"><Card className="p-6">
    <h2 id="policy-model-h" className="font-semibold">Allowed models</h2>
    <p className="mt-1 max-w-prose text-text-muted">Limit which models your keys can use, for example to keep calls on approved models. The model a call asks for, or the default if it names none, is checked against this list.</p>
    <form onSubmit={save} className="mt-4 space-y-5">
      <ModeFieldset name="model-mode" value={mode} onChange={setMode} options={OPTIONS} disabled={!canEdit} />
      <div>
        <label htmlFor="models" className="mb-1 block text-sm font-medium">Models on the list</label>
        <textarea id="models" rows={6} readOnly={!canEdit} spellCheck={false} value={text} onChange={e => setText(e.target.value)} placeholder={'claude-*\ngpt-4o'} className="w-full rounded-md border border-border-input bg-bg p-3 font-mono text-sm" />
        <p className="mt-1 text-xs text-text-muted">One per line. <span className="font-mono">*</span> matches any characters and <span className="font-mono">?</span> one character. Not case sensitive. Up to 50 entries. <span className="font-mono">gpt-4o</span> matches only that model, not <span className="font-mono">gpt-4o-mini</span>.</p>
      </div>
      <SaveRow canEdit={canEdit} busy={busy} dirty={dirty} msg={msg} />
    </form>
    {canEdit && <form onSubmit={check} className="mt-6 border-t border-border pt-4">
      <h3 className="text-sm font-semibold">Try a model name</h3>
      <p className="mt-1 text-xs text-text-muted">Checks a name against the saved policy. Nothing is sent to a provider.</p>
      <div className="mt-2 flex flex-wrap items-end gap-3">
        <div className="min-w-60 flex-1"><label htmlFor="probe" className="mb-1 block text-sm font-medium">Model</label>
          <input id="probe" required maxLength={200} value={probe} onChange={e => setProbe(e.target.value)} placeholder="e.g. claude-sonnet-5-5" className="h-10 w-full rounded-md border border-border-input bg-bg px-3 font-mono" /></div>
        <Button type="submit" variant="secondary">Check</Button>
      </div>
      {probeResult && <output className="mt-3 block text-sm">{probeResult}</output>}
    </form>}
  </Card></section>
}
