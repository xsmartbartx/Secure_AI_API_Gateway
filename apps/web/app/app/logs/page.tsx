'use client'
import { useSearchParams } from 'next/navigation'
import { Suspense, useRef, useState } from 'react'
import { Card, Empty, ErrorState, PageHeader, Pill, Skeleton, Td, Th } from '@/components/ui'
import type { Log } from '@/lib/api'
import { useApi } from '@/lib/use-fetch'

function Logs() {
  const sp = useSearchParams()
  const [decision, setDecision] = useState(sp.get('decision') ?? '')
  const { data, error, loading, reload } = useApi<{ items: Log[] }>(`/api/logs?limit=100${decision ? `&decision=${decision}` : ''}`)
  const [sel, setSel] = useState<Log | null>(null)
  const opener = useRef<HTMLElement | null>(null)
  const open = (l: Log, el: HTMLElement) => { opener.current = el; setSel(l) }
  const close = () => { setSel(null); opener.current?.focus() } // hand focus back to the row that opened the drawer
  return <>
    <PageHeader title="Logs" description="Every call, with its decision. Prompt text is never stored, only a hash."
      action={<div><label htmlFor="d" className="sr-only">Filter by decision</label><select id="d" value={decision} onChange={e => setDecision(e.target.value)} className="h-10 rounded-md border border-border-input bg-bg px-3">
        <option value="">All decisions</option><option value="allow">Allowed</option><option value="block">Blocked</option><option value="error">Errors</option></select></div>} />
    <Card className="overflow-x-auto">
      {loading && <div className="space-y-3 p-4">{[0, 1, 2, 3].map(i => <Skeleton key={i} className="h-6" />)}</div>}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && data.items.length === 0 && <Empty title={decision ? 'No matching calls' : 'No calls logged yet'} help={decision ? 'Clear the filter to see everything.' : 'Calls appear here as soon as they finish.'} />}
      {data && data.items.length > 0 && <table className="w-full text-sm"><thead className="border-b border-border"><tr><Th>Time</Th><Th>Decision</Th><Th>Model</Th><Th>Tokens</Th><Th>Latency</Th><Th>Status</Th></tr></thead>
        <tbody className="divide-y divide-border">{data.items.map(l => <tr key={l.id} tabIndex={0} onClick={e => open(l, e.currentTarget)}
          // preventDefault: the drawer's close button takes focus while this key is still down, and the browser would then press it
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(l, e.currentTarget) } }} className="cursor-pointer hover:bg-surface">
          <Td className="whitespace-nowrap">{new Date(l.ts).toLocaleString()}</Td><Td><Pill decision={l.decision} /></Td><Td className="max-w-40 truncate">{l.model}</Td>
          <Td>{l.tokens_in + l.tokens_out}</Td><Td>{l.latency_ms ?? '–'} ms</Td><Td>{l.status_code === 499 ? '499 · cancelled by client' : l.status_code}</Td></tr>)}</tbody></table>}
    </Card>
    {sel && <div role="dialog" aria-modal="true" aria-label="Request details" onKeyDown={e => e.key === 'Escape' && close()} className="fixed inset-y-0 right-0 z-30 w-full overflow-y-auto border-l border-border bg-surface-raised p-6 shadow-pop sm:w-[480px]">
      <div className="mb-4 flex items-center justify-between"><h2 className="text-lg font-semibold">Request details</h2><button autoFocus className="rounded p-2 hover:bg-surface" onClick={close} aria-label="Close details">✕</button></div>
      <dl className="space-y-3 text-sm">{([['Request ID', sel.request_id], ['Time', new Date(sel.ts).toISOString()], ['Provider', sel.provider], ['Model', sel.model], ['Decision', sel.decision], ['HTTP status', sel.status_code], ['Tokens in / out', `${sel.tokens_in} / ${sel.tokens_out}`], ['Latency', `${sel.latency_ms ?? '–'} ms`]] as const).map(([k, v]) => <div key={k}><dt className="text-text-muted">{k}</dt><dd className="break-all font-mono text-[13px]">{String(v ?? '–')}</dd></div>)}</dl>
    </div>}
  </>
}
export default function LogsPage() { return <Suspense><Logs /></Suspense> }
