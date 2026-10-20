'use client'
import { useState } from 'react'
import { Button, Card } from '@/components/ui'
import { api } from '@/lib/api'

type Scan = { findings: { kind: string; label: string; category: string; count: number }[]; injection: { kind: string; label: string; count: number }[]; score: number; masked: string }

export function ScanTester() {
  const [text, setText] = useState('')
  const [result, setResult] = useState<Scan | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function scan(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null); setResult(null)
    try { setResult(await api<Scan>('/api/policies/scan', { method: 'POST', body: JSON.stringify({ text }) })) }
    catch (error: any) { setErr(error.message) } finally { setBusy(false) }
  }
  const nothing = result && result.findings.length === 0 && result.injection.length === 0

  return <section aria-labelledby="policy-scan-h"><Card className="p-6">
    <h2 id="policy-scan-h" className="font-semibold">Try the detectors</h2>
    <p className="mt-1 max-w-prose text-sm text-text-muted">Paste a sample to see what would be found, whatever your policies are set to. The text is sent to Gateway for this check only and is not stored or logged. Use made-up examples, not real personal data or secrets.</p>
    <form onSubmit={scan} className="mt-3 space-y-3">
      <div><label htmlFor="scan-text" className="mb-1 block text-sm font-medium">Sample text</label>
        <textarea id="scan-text" required rows={4} maxLength={20000} value={text} onChange={e => setText(e.target.value)} spellCheck={false} className="w-full rounded-md border border-border-input bg-bg p-3 font-mono text-sm" /></div>
      <Button type="submit" variant="secondary" loading={busy}>Scan</Button>
    </form>
    {err && <p role="alert" className="mt-3 text-sm text-danger">{err}</p>}
    {result && <output className="mt-4 block space-y-2 text-sm">
      {nothing && <p>Nothing found.</p>}
      {result.findings.map(f => <p key={f.kind}><span className="font-medium">{f.label}</span> × {f.count} <span className="text-text-muted">({f.category})</span></p>)}
      {result.injection.map(f => <p key={f.kind}><span className="font-medium">Possible injection: {f.label}</span> × {f.count}</p>)}
      {!nothing && <p className="text-text-muted">Risk score {result.score} of 100.</p>}
      {result.findings.length > 0 && <div><p className="font-medium">With masking:</p><pre className="mt-1 overflow-x-auto whitespace-pre-wrap rounded-md border border-border bg-surface p-3 font-mono text-xs">{result.masked}</pre></div>}
    </output>}
  </Card></section>
}
