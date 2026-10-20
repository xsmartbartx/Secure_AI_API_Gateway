'use client'
import { useEffect, useState } from 'react'
import { Card } from '@/components/ui'
import { api } from '@/lib/api'
import { Mode, ModeFieldset, SaveRow } from './shared'

export type InjectionPolicy = { mode: Mode; version: number }

const OPTIONS = [
  { value: 'off' as const, label: 'Off', help: 'Calls are not checked for injection attempts.' },
  { value: 'monitor' as const, label: 'Monitor', help: 'Calls go through. Suspected attempts are flagged in Logs and Security events. Start here.' },
  { value: 'enforce' as const, label: 'Enforce', help: 'Calls with a suspected attempt are rejected before they reach the provider.' },
]

export function InjectionCard({ policy, canEdit, onSaved }: Readonly<{ policy: InjectionPolicy; canEdit: boolean; onSaved: () => void }>) {
  const [mode, setMode] = useState<Mode>(policy.mode)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  useEffect(() => setMode(policy.mode), [policy])

  async function save(e: React.FormEvent) {
    e.preventDefault(); setMsg(null)
    if (mode === 'enforce' && policy.mode !== 'enforce' && !confirm('Turn on enforcement? Calls that look like injection attempts are rejected immediately. This check is a heuristic and can reject harmless text.')) return
    setBusy(true)
    try { const r = await api<InjectionPolicy>('/api/policies/injection', { method: 'PUT', body: JSON.stringify({ mode }) }); setMsg({ ok: true, text: `Saved (version ${r.version}).` }); onSaved() }
    catch (err: any) { setMsg({ ok: false, text: err.message }) } finally { setBusy(false) }
  }

  return <section aria-labelledby="policy-inj-h"><Card className="p-6">
    <h2 id="policy-inj-h" className="font-semibold">Prompt injection</h2>
    <p className="mt-1 max-w-prose text-text-muted">Matches known phrases, such as telling the model to ignore its instructions or reveal its system prompt. It checks user and assistant turns, not your own system prompt. It is a heuristic: it will miss some attacks and can flag harmless text, so use Monitor first.</p>
    <form onSubmit={save} className="mt-4 space-y-5">
      <ModeFieldset name="inj-mode" value={mode} onChange={setMode} options={OPTIONS} disabled={!canEdit} />
      <SaveRow canEdit={canEdit} busy={busy} dirty={mode !== policy.mode} msg={msg} />
    </form>
  </Card></section>
}
