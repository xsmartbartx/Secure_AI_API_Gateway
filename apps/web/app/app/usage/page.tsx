'use client'
import { Card, Empty, ErrorState, PageHeader, Skeleton, Td, Th } from '@/components/ui'
import { useApi } from '@/lib/use-fetch'

export default function Usage() {
  const { data, error, loading, reload } = useApi<{ by_model: { model: string; calls: number; tokens_in: number; tokens_out: number }[] }>('/api/usage?days=30')
  return <>
    <PageHeader title="Usage" description="Last 30 days, by model. Token counts come from the provider's own response." />
    <Card className="overflow-x-auto">
      {loading && <div className="space-y-3 p-4"><Skeleton className="h-6" /><Skeleton className="h-6" /></div>}
      {error && <ErrorState message={error.message} onRetry={reload} />}
      {data && data.by_model.length === 0 && <Empty title="No usage yet" help="Usage is summarized here after your first call." />}
      {data && data.by_model.length > 0 && <table className="w-full text-sm"><thead className="border-b border-border"><tr><Th>Model</Th><Th>Calls</Th><Th>Tokens in</Th><Th>Tokens out</Th></tr></thead>
        <tbody className="divide-y divide-border">{data.by_model.map(m => <tr key={m.model}><Td className="font-medium">{m.model}</Td><Td>{m.calls}</Td><Td>{m.tokens_in.toLocaleString()}</Td><Td>{m.tokens_out.toLocaleString()}</Td></tr>)}</tbody></table>}
    </Card>
    <p className="mt-3 text-xs text-text-muted">Cost estimates are not shown yet. Your provider's invoice is the source of truth.</p>
  </>
}
