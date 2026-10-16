'use client'
import Link from 'next/link'
import { BarSeries } from '@/components/charts'
import { Button, Card, Empty, ErrorState, PageHeader, Skeleton } from '@/components/ui'
import type { Overview } from '@/lib/api'
import { useApi } from '@/lib/use-fetch'

function Tile({ label, value, href }: { label: string; value: string; href: string }) {
  return <Link href={href}><Card className="p-4 hover:border-accent"><p className="text-xs font-medium text-text-muted">{label}</p><p className="mt-1 text-[28px] font-semibold leading-[34px]">{value}</p></Card></Link>
}

export default function OverviewPage() {
  const { data, error, loading, reload } = useApi<Overview>('/api/overview?days=7')
  return <>
    <PageHeader title="Overview" description="Last 7 days across all keys." action={<Link href="/app/keys"><Button variant="secondary">Manage keys</Button></Link>} />
    {loading && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map(i => <Card key={i} className="space-y-3 p-4"><Skeleton className="w-20" /><Skeleton className="h-8 w-28" /></Card>)}</div>}
    {error && <Card><ErrorState message={error.message} onRetry={reload} /></Card>}
    {data && data.calls === 0 && <Card><Empty title="No calls yet" help="Create a key and make your first request. It will show up here within seconds." action={<Link href="/app/keys"><Button>Create your first key</Button></Link>} /></Card>}
    {data && data.calls > 0 && <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Tile label="Calls" value={data.calls.toLocaleString()} href="/app/logs" />
        <Tile label="Blocked" value={data.blocked.toLocaleString()} href="/app/logs?decision=block" />
        <Tile label="Median latency" value={data.p50_latency_ms != null ? `${data.p50_latency_ms} ms` : '–'} href="/app/logs" />
        <Tile label="Monthly quota" value={`${data.quota.used} / ${data.quota.limit}`} href="/app/billing" />
      </div>
      <Card className="p-4"><h2 className="mb-3 font-semibold">Calls per day</h2><BarSeries data={data.series} label="Calls per day, blocked calls in red" /></Card>
    </div>}
  </>
}
