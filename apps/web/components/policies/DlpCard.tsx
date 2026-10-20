'use client'
import { useEffect, useState } from 'react'
import { Card } from '@/components/ui'
import { api } from '@/lib/api'
import { Mode, ModeFieldset, SaveRow } from './shared'

export type DlpPolicy = { mode: Mode; detectors: string[]; action: 'block' | 'mask'; available: string[]; labels: Record<string, string>; version: number }

/** Whether two lists hold the same entries, in any order. */
const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every(x => b.includes(x))

const OPTIONS = [
  { value: 'off' as const, label: 'Off', help: 'Calls are not inspected for sensitive data.' },
  { value: 'monitor' as const, label: 'Monitor', help: 'Calls go through untouched. Anything found is flagged in Logs and Security events, so you can see what a rule would catch.' },
  { value: 'enforce' as const, label: 'Enforce', help: 'Found data is dealt with before the call reaches the provider: blocked, or masked, as chosen below.' },
]

export function DlpCard({ policy, canEdit, onSaved }: Readonly<{ policy: DlpPolicy; canEdit: boolean; onSaved: () => void }>) {
  const [mode, setMode] = useState<Mode>(policy.mode)
  const [detectors, setDetectors] = useState<string[]>(policy.detectors)
  const [action, setAction] = useState<'block' | 'mask'>(policy.action)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  useEffect(() => { setMode(policy.mode); setDetectors(policy.detectors); setAction(policy.action) }, [policy])
  const dirty = mode !== policy.mode || action !== policy.action || !sameSet(detectors, policy.detectors)
  const toggle = (k: string) => setDetectors(d => d.includes(k) ? d.filter(x => x !== k) : [...d, k])

  async function save(e: React.FormEvent) {
    e.preventDefault(); setMsg(null)
    if (mode === 'enforce' && policy.mode !== 'enforce' && !confirm(action === 'block' ? 'Turn on enforcement? Calls that contain the selected kinds of data are rejected immediately.' : 'Turn on masking? The selected kinds of data are replaced with placeholders before the call is sent to the provider.')) return
    setBusy(true)
    try { const r = await api<DlpPolicy>('/api/policies/dlp', { method: 'PUT', body: JSON.stringify({ mode, detectors, action }) }); setMsg({ ok: true, text: `Saved (version ${r.version}).` }); onSaved() }
    catch (err: any) { setMsg({ ok: false, text: err.message }) } finally { setBusy(false) }
  }

  return <section aria-labelledby="policy-dlp-h"><Card className="p-6">
    <h2 id="policy-dlp-h" className="font-semibold">Sensitive data</h2>
    <p className="mt-1 max-w-prose text-text-muted">Looks for personal, financial and secret data in every message of a call, including the system prompt and earlier turns. Card numbers, IBANs and PESEL are checked with their check digits to avoid false alarms.</p>
    <form onSubmit={save} className="mt-4 space-y-5">
      <ModeFieldset name="dlp-mode" value={mode} onChange={setMode} options={OPTIONS} disabled={!canEdit} />
      <fieldset disabled={!canEdit} className="space-y-2">
        <legend className="mb-1 text-sm font-medium">What to look for</legend>
        <div className="grid gap-2 sm:grid-cols-2">{policy.available.map(k => <label key={k} className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={detectors.includes(k)} onChange={() => toggle(k)} />{policy.labels[k] ?? k}</label>)}</div>
      </fieldset>
      {mode === 'enforce' && <fieldset disabled={!canEdit} className="space-y-2">
        <legend className="mb-1 text-sm font-medium">When something is found</legend>
        <label className="flex items-start gap-2 text-sm"><input type="radio" name="dlp-action" checked={action === 'block'} onChange={() => setAction('block')} className="mt-1" /><span><span className="font-medium">Block the call.</span> It is rejected and logged as blocked; nothing reaches the provider and it does not use your quota.</span></label>
        <label className="flex items-start gap-2 text-sm"><input type="radio" name="dlp-action" checked={action === 'mask'} onChange={() => setAction('mask')} className="mt-1" /><span><span className="font-medium">Mask it.</span> Each match becomes a placeholder such as [REDACTED:card] and the call goes ahead. The provider never sees the original.</span></label>
      </fieldset>}
      <SaveRow canEdit={canEdit} busy={busy} dirty={dirty} msg={msg} />
    </form>
  </Card></section>
}
