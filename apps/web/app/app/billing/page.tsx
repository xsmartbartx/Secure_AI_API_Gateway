'use client'
import { Button, Card, Meter, PageHeader, Skeleton } from '@/components/ui'
import { useApi } from '@/lib/use-fetch'
import { api } from '@/lib/api'
import { useState } from 'react'
import type { Overview } from '@/lib/api'

export default function Billing() {
  const bill = useApi<{ enabled: boolean; status: string; can_manage: boolean }>('/api/billing')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  async function go(path: string) {
    setBusy(true); setErr(null)
    try { const r = await api<{ url: string }>(path, { method: 'POST' }); window.location.href = r.url } catch (e: any) { setErr(e.message); setBusy(false) }
  }
  const me = useApi<{ org: { plan: string; quota: number } }>('/api/me')
  const ov = useApi<Overview>('/api/overview?days=30')
  const used = ov.data?.quota.used ?? 0, limit = me.data?.org.quota ?? 0
  const pct = limit ? Math.min(100, Math.round((used / limit) * 100)) : 0
  return <>
    <PageHeader title="Billing" description="Your plan and this month's usage." />
    <div className="grid gap-6 lg:grid-cols-2">
      <Card className="p-6">
        <p className="text-xs font-medium text-text-muted">Current plan</p>
        {me.loading ? <Skeleton className="mt-2 h-7 w-24" /> : <p className="mt-1 text-[28px] font-semibold capitalize leading-[34px]">{me.data?.org.plan}</p>}
        <div className="mt-6"><div className="flex justify-between text-sm"><span>Calls this month</span><span>{used} / {limit}</span></div>
          <Meter pct={pct} label="Monthly quota used" className="mt-2 h-2" />
          {pct >= 80 && <p className="mt-2 text-sm text-warning">You have used {pct}% of this month's calls.</p>}</div>
      </Card>
      <Card className="p-6"><h2 className="font-semibold">Starter · $19 / month</h2><p className="mt-1 text-text-muted">1,500 calls per month.</p>
        {bill.data?.can_manage
          ? <Button className="mt-6" variant="secondary" loading={busy} onClick={() => go('/api/billing/portal')}>Manage or cancel plan</Button>
          : <Button className="mt-6" loading={busy} disabled={!bill.data?.enabled} onClick={() => go('/api/billing/checkout')}>Upgrade to Starter</Button>}
        {bill.data && !bill.data.enabled && <p className="mt-3 text-xs text-text-muted">Online checkout is not enabled yet. To upgrade now, contact us from onenexora.com.</p>}
        {bill.data?.status === 'past_due' && <p role="alert" className="mt-3 text-sm text-danger">Your last payment failed. Update your card in the billing portal.</p>}
        {err && <p role="alert" className="mt-3 text-sm text-danger">{err}</p>}
        </Card>
    </div>
  </>
}
