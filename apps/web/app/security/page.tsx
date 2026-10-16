import type { Metadata } from 'next'
import { MarketingShell, Section } from '@/components/marketing'

export const metadata: Metadata = { title: 'Security' }
export default function Security() {
  const live = [['Keys stored as hashes', 'Gateway keys are shown once. Only a SHA-256 hash is stored, with the last four characters for identification.'], ['Provider keys stay server-side', 'Your applications never hold the model provider key.'], ['Per-organization isolation', 'Every query is scoped to your organization, and tested for cross-tenant access.'], ['Model policy', 'Allow only the models you approve. Monitor mode shows what would be blocked; enforce mode rejects the call before it reaches a provider.'], ['Audit log without prompts', 'We log the decision, model, tokens, latency, and a hash of the prompt, not the prompt itself.']]
  const next = ['Data loss prevention for emails, card numbers, IBANs, and secrets', 'Prompt-injection detection, starting in monitor mode', 'More policy rules, such as spend limits and per-key rules', 'SIEM export for Splunk, Sentinel, and Elastic']
  return <MarketingShell><Section>
    <h1 className="max-w-3xl text-[40px] font-bold leading-[44px] tracking-tight">Security that says what exists today.</h1>
    <p className="mt-4 max-w-prose text-text-muted">No badge wall. Here is what Gateway does now, and what is still being built.</p>
    <h2 className="mt-16 text-[28px] font-semibold leading-[34px]">Live</h2>
    <div className="mt-6 grid gap-6 md:grid-cols-2">{live.map(([t, d]) => <div key={t} className="rounded-lg border border-border bg-surface-raised p-6 shadow-card"><h3 className="font-semibold">{t}</h3><p className="mt-2 text-text-muted">{d}</p></div>)}</div>
    <h2 className="mt-16 text-[28px] font-semibold leading-[34px]">Coming</h2>
    <ul className="mt-6 space-y-3 text-text-muted">{next.map(x => <li key={x}>○ {x}</li>)}</ul>
  </Section></MarketingShell>
}
