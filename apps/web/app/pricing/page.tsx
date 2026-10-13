import type { Metadata } from 'next'
import Link from 'next/link'
import { MarketingShell, Section } from '@/components/marketing'

export const metadata: Metadata = { title: 'Pricing' }
const plans = [
  { name: 'Free', price: '$0', calls: '100 calls / month', note: 'Try the full loop.', cta: 'Start free', href: '/app' },
  { name: 'Starter', price: '$19', calls: '1,500 calls / month', note: 'For a small production workload.', cta: 'Choose Starter', href: '/app/billing', featured: true },
  { name: 'Team', price: 'Contact us', calls: 'Custom volume', note: 'Roles, higher limits, and priority support.', cta: 'Talk to us', href: 'https://onenexora.com/company#contact' },
]
export default function Pricing() {
  return <MarketingShell><Section>
    <h1 className="text-center text-[40px] font-bold leading-[44px] tracking-tight">Simple, call-based pricing</h1>
    <p className="mx-auto mt-4 max-w-prose text-center text-text-muted">Gateway pricing covers governance and logging. You pay your model provider separately for tokens.</p>
    <div className="mt-12 grid gap-6 md:grid-cols-3">
      {plans.map(p => <div key={p.name} className={`rounded-lg border bg-surface-raised p-6 shadow-card ${p.featured ? 'border-accent' : 'border-border'}`}>
        <h2 className="text-xl font-semibold">{p.name}</h2>
        <p className="mt-4 text-[28px] font-bold leading-[34px]">{p.price}{p.price.startsWith('$') && p.price !== '$0' && <span className="text-sm font-normal text-text-muted"> / month</span>}</p>
        <p className="mt-2 font-medium">{p.calls}</p><p className="mt-1 text-text-muted">{p.note}</p>
        <Link href={p.href} className={`mt-6 inline-flex h-10 w-full items-center justify-center rounded-md text-sm font-semibold ${p.featured ? 'bg-accent text-on-accent hover:bg-accent-hover' : 'border border-border-input hover:bg-surface'}`}>{p.cta}</Link>
      </div>)}
    </div>
    <h2 className="mt-24 text-[28px] font-semibold leading-[34px]">Questions</h2>
    <dl className="mt-6 grid gap-6 md:grid-cols-2">
      {[['What counts as a call?', 'Each successful request through /v1/chat. Rejected and failed requests do not count.'], ['What happens at the limit?', 'Further calls return a 429 quota_exceeded error until the month resets or you upgrade.'], ['Do you store my prompts?', 'No. Gateway stores a hash of each prompt, with model, tokens, latency, and decision.']].map(([q, a]) => <div key={q}><dt className="font-semibold">{q}</dt><dd className="mt-1 text-text-muted">{a}</dd></div>)}
    </dl>
  </Section></MarketingShell>
}
