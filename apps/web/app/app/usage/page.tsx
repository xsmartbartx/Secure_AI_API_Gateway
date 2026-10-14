'use client'
import { useState } from 'react'
import { BarSeries } from '@/components/charts'
import { Button, Card, Empty, ErrorState, PageHeader, Skeleton, Td, Th } from '@/components/ui'
import { apiDownload, Usage } from '@/lib/api'
import { useApi } from '@/lib/use-fetch'

const GROUPS = [['key', 'By key'], ['model', 'By model'], ['day', 'By day']] as const
const utcDay = (offset = 0) => new Date(Date.now() + offset * 86_400_000).toISOString().slice(0, 10)
const n = (v: number) => v.toLocaleString()

// The API returns only days that had calls; the chart needs every day so gaps look like gaps.
function fillDays(rows: { label: string; calls: number; blocked: number }[], from: string, to: string) {
  const byDay = new Map(rows.map(r => [r.label, r]))
  const out: { day: string; calls: number; blocked: number }[] = []
  for (let t = Date.parse(from); t <= Date.parse(to) && out.length < 367; t += 86_400_000) {
    const d = new Date(t).toISOString().slice(0, 10)
    out.push({ day: d, calls: byDay.get(d)?.calls ?? 0, blocked: byDay.get(d)?.blocked ?? 0 })
  }
  return out
}

export default function UsagePage() {
  const [group, setGroup] = useState<'key' | 'model' | 'day'>('key')
  const [from, setFrom] = useState(utcDay(-29))
  const [to, setTo] = useState(utcDay())
  const [err, setErr] = useState<string | null>(null)
  const valid = from <= to
  const qs = `from=${from}&to=${to}&group=${group}`
  const { data, error, loading, reload } = useApi<Usage>(valid ? `/api/usage?${qs}` : '/api/usage?group=' + group)

  const preset = (days: number) => { setFrom(utcDay(-(days - 1))); setTo(utcDay()) }
  async function csv() {
    setErr(null)
    try { await apiDownload(`/api/usage?${qs}&format=csv`, `usage-${group}.csv`) } catch (e: any) { setErr(e.message) }
  }

  return <>
    <PageHeader title="Usage" description="Calls and tokens per key, model or day. Days are UTC. Token counts come from the provider's response (estimated for cancelled streams)."
      action={<Button variant="secondary" onClick={csv} disabled={!data || data.rows.length === 0}>Download CSV</Button>} />
    <Card className="mb-6 flex flex-wrap items-end gap-4 p-4">
      <div role="group" aria-label="Group by" className="flex overflow-hidden rounded-md border border-border-input">
        {GROUPS.map(([g, label]) => <button key={g} aria-pressed={group === g} onClick={() => setGroup(g)}
          className={`h-10 px-4 text-sm font-medium ${group === g ? 'bg-accent text-on-accent' : 'bg-bg hover:bg-surface'}`}>{label}</button>)}
      </div>
      <div><label htmlFor="from" className="mb-1 block text-xs font-medium text-text-muted">From</label>
        <input id="from" type="date" value={from} max={to} onChange={e => setFrom(e.target.value)} className="h-10 rounded-md border border-border-input bg-bg px-3" /></div>
      <div><label htmlFor="to" className="mb-1 block text-xs font-medium text-text-muted">To</label>
        <input id="to" type="date" value={to} min={from} max={utcDay()} onChange={e => setTo(e.target.value)} className="h-10 rounded-md border border-border-input bg-bg px-3" /></div>
      <div className="flex gap-2">{[7, 30, 90].map(d => <Button key={d} size="sm" variant="ghost" onClick={() => preset(d)}>Last {d}d</Button>)}</div>
      {!valid && <p role="alert" className="w-full text-sm text-danger">"From" must not be after "To".</p>}
    </Card>
    {err && <p role="alert" className="mb-4 text-sm text-danger">{err}</p>}

    {data && group === 'day' && data.rows.length > 0 && <Card className="mb-6 p-4"><h2 className="mb-3 font-semibold">Calls per day</h2>
      <BarSeries data={fillDays(data.rows, data.from, data.to)} label="Calls per day, blocked calls in red" /></Card>}

    <Card className="overflow-x-auto">
      {loading && <div className="space-y-3 p-4">{[0, 1, 2].map(i => <Skeleton key={i} className="h-6" />)}</div>}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && !loading && data.rows.length === 0 && <Empty title="No calls in this range" help="Try a wider range, or make a call from the playground." />}
      {data && !loading && data.rows.length > 0 && <table className="w-full text-sm">
        <thead className="border-b border-border"><tr><Th>{group === 'key' ? 'Key' : group === 'model' ? 'Model' : 'Day'}</Th><Th>Calls</Th><Th>Blocked</Th><Th>Errors</Th><Th>Tokens in</Th><Th>Tokens out</Th></tr></thead>
        <tbody className="divide-y divide-border">{data.rows.map(r => <tr key={r.id ?? r.label}>
          <Td className="max-w-56 truncate font-medium">{r.label}{r.revoked && <span className="ml-2 text-xs font-normal text-text-muted">revoked</span>}
            {r.prefix && <span className="block font-mono text-xs font-normal text-text-muted">{r.prefix}</span>}</Td>
          <Td>{n(r.calls)}</Td><Td>{n(r.blocked)}</Td><Td>{n(r.errors)}</Td><Td>{n(r.tokens_in)}</Td><Td>{n(r.tokens_out)}</Td></tr>)}</tbody>
        <tfoot className="border-t border-border bg-surface font-semibold"><tr><Td>Total</Td><Td>{n(data.totals.calls)}</Td><Td>{n(data.totals.blocked)}</Td><Td>{n(data.totals.errors)}</Td><Td>{n(data.totals.tokens_in)}</Td><Td>{n(data.totals.tokens_out)}</Td></tr></tfoot>
      </table>}
    </Card>
    <p className="mt-3 text-xs text-text-muted">Cost estimates are not shown. Your provider's invoice is the source of truth.</p>
  </>
}
