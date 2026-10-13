import { Card, PageHeader } from '@/components/ui'
export default function Page() {
  return <><PageHeader title="Providers" description="Connect your own provider credentials and choose routing rules. Today Gateway uses one provider configured by NEXORA." />
    <Card className="p-8 text-center"><p className="text-base font-semibold">On the roadmap</p><p className="mx-auto mt-1 max-w-sm text-text-muted">This part of Gateway is not available yet. We list it here so you can see what is coming.</p></Card></>
}
