'use client'
import { useState } from 'react'
import { Button, Card, PageHeader } from '@/components/ui'
import { api } from '@/lib/api'

export default function Playground() {
  const [prompt, setPrompt] = useState('')
  const [system, setSystem] = useState('')
  const [out, setOut] = useState<{ text: string; usage: string } | null>(null)
  const [err, setErr] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function run(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setErr(null); setOut(null)
    try {
      const r = await api<any>('/api/playground', { method: 'POST', body: JSON.stringify({ prompt, system: system || undefined }) })
      setOut({ text: r.choices[0].message.content, usage: `${r.usage.total_tokens} tokens · ${r.provider} · ${r.model}` })
    } catch (e: any) { setErr(e.message) } finally { setBusy(false) }
  }
  return <>
    <PageHeader title="Playground" description="Send a test prompt through your organization's pipeline. No key needed. Calls count toward your quota." />
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="p-4"><form onSubmit={run} className="space-y-4">
        <div><label htmlFor="sys" className="mb-1 block text-sm font-medium">System prompt <span className="font-normal text-text-muted">(optional)</span></label>
          <textarea id="sys" rows={3} value={system} onChange={e => setSystem(e.target.value)} className="w-full rounded-md border border-border-input bg-bg p-3" /></div>
        <div><label htmlFor="pr" className="mb-1 block text-sm font-medium">Message</label>
          <textarea id="pr" required rows={7} value={prompt} onChange={e => setPrompt(e.target.value)} className="w-full rounded-md border border-border-input bg-bg p-3" /></div>
        <Button type="submit" loading={busy}>Send</Button>
      </form></Card>
      <Card className="p-4" aria-live="polite">
        <h2 className="mb-3 font-semibold">Response</h2>
        {!out && !err && !busy && <p className="text-text-muted">Your response will appear here.</p>}
        {busy && <p className="text-text-muted">Waiting for the provider…</p>}
        {err && <p role="alert" className="text-danger">{err}</p>}
        {out && <><p className="whitespace-pre-wrap">{out.text}</p><p className="mt-4 text-xs text-text-muted">{out.usage}</p></>}
      </Card>
    </div>
  </>
}
