'use client'
import { Card, ErrorState, PageHeader, Skeleton } from '@/components/ui'
import { DlpCard, DlpPolicy } from '@/components/policies/DlpCard'
import { InjectionCard, InjectionPolicy } from '@/components/policies/InjectionCard'
import { ModelCard, ModelPolicy } from '@/components/policies/ModelCard'
import { ScanTester } from '@/components/policies/ScanTester'
import { useApi } from '@/lib/use-fetch'

type Policies = { model_allow: ModelPolicy; dlp: DlpPolicy; injection: InjectionPolicy }

export default function PoliciesPage() {
  const { data, error, loading, reload } = useApi<Policies>('/api/policies')
  const me = useApi<{ member: { role: string } }>('/api/me')
  const canEdit = me.data?.member.role === 'admin' || me.data?.member.role === 'owner'

  return <>
    <PageHeader title="Policies" description="Rules applied to every call before it is sent to a provider." />
    {loading && <Card className="space-y-3 p-6"><Skeleton className="w-48" /><Skeleton className="h-24 w-full" /></Card>}
    {error && <Card><ErrorState message={error.message} onRetry={reload} /></Card>}
    {data && <div className="space-y-6">
      <ModelCard policy={data.model_allow} canEdit={canEdit} onSaved={reload} />
      <DlpCard policy={data.dlp} canEdit={canEdit} onSaved={reload} />
      <InjectionCard policy={data.injection} canEdit={canEdit} onSaved={reload} />
      {canEdit && <ScanTester />}
      <Card className="p-6">
        <h2 className="font-semibold">Where blocked and flagged calls show up</h2>
        <p className="mt-1 max-w-prose text-sm text-text-muted">In Logs (filter by decision), in Security events, and in the Overview. Blocked calls never reach a provider and do not use your quota. Policies are checked in this order: model, then sensitive data, then prompt injection.</p>
      </Card>
    </div>}
  </>
}
