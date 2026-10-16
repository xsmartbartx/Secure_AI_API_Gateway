'use client'
import { Card, Empty, ErrorState, PageHeader, Skeleton, Td, Th } from '@/components/ui'
import { useApi } from '@/lib/use-fetch'

const LABELS: Record<string, string> = { policy_denied: 'Call blocked: model not allowed', policy_would_deny: 'Call flagged: model not on the list (monitor mode)' }

export default function SecurityEvents() {
  const { data, error, loading, reload } = useApi<{ items: { id: string; type: string; severity: string; ts: string; excerpt: string | null }[] }>('/api/security-events')
  return <>
    <PageHeader title="Security events" description="Flags and blocks raised by your policies." />
    <Card>
      {loading && <div className="p-4"><Skeleton className="h-6" /></div>}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && data.items.length === 0 && <Empty title="No security events" help="Calls blocked or flagged by your model policy appear here. Detection for data leaks and prompt injection is on the roadmap." />}
      {data && data.items.length > 0 && <table className="w-full text-sm"><thead className="border-b border-border"><tr><Th>Time</Th><Th>Event</Th><Th>Detail</Th><Th>Severity</Th></tr></thead>
        <tbody className="divide-y divide-border">{data.items.map(e => <tr key={e.id}><Td>{new Date(e.ts).toLocaleString()}</Td><Td>{LABELS[e.type] ?? e.type}</Td><Td className="font-mono text-xs">{e.excerpt ?? ''}</Td><Td>{e.severity}</Td></tr>)}</tbody></table>}
    </Card>
  </>
}
