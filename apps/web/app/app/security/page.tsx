'use client'
import { Card, Empty, ErrorState, PageHeader, Skeleton, Td, Th } from '@/components/ui'
import { useApi } from '@/lib/use-fetch'

export default function SecurityEvents() {
  const { data, error, loading, reload } = useApi<{ items: { id: string; type: string; severity: string; ts: string }[] }>('/api/security-events')
  return <>
    <PageHeader title="Security events" description="Flags and blocks raised by your policies." />
    <Card>
      {loading && <div className="p-4"><Skeleton className="h-6" /></div>}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && data.items.length === 0 && <Empty title="No security events" help="Detection for data leaks and prompt injection is on the roadmap. Rate-limit and quota rejections appear in Logs." />}
      {data && data.items.length > 0 && <table className="w-full text-sm"><thead className="border-b border-border"><tr><Th>Time</Th><Th>Type</Th><Th>Severity</Th></tr></thead>
        <tbody className="divide-y divide-border">{data.items.map(e => <tr key={e.id}><Td>{new Date(e.ts).toLocaleString()}</Td><Td>{e.type}</Td><Td>{e.severity}</Td></tr>)}</tbody></table>}
    </Card>
  </>
}
