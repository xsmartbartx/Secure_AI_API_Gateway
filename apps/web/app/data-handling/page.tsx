import type { Metadata } from 'next'
import { MarketingShell, Section } from '@/components/marketing'

export const metadata: Metadata = { title: 'Data handling' }

const rows = [
  ['Gateway API keys', 'A SHA-256 hash, the first characters of the key, and the last four. The full key is shown once at creation.', 'Until you revoke the key'],
  ['Prompts and responses', 'Not stored. A hash of the prompt is kept so repeated requests can be recognized.', 'Prompt text is never written'],
  ['Request log', 'Time, model, provider, token counts, latency, status, decision, request ID.', 'Free 7 days, Starter 30 days, deleted within a day after that'],
  ['Daily usage counts', 'Calls, blocked, errors and token counts per day, key and model. No content, no prompts.', 'Until you delete the organization'],
  ['Provider keys you add', 'Checked with the provider, then encrypted at rest (AES-256-GCM). Never returned by the API or shown again, only the last four characters. Without one, calls use the shared key NEXORA configures.', 'Until you remove the key or delete the organization'],
  ['Account and organization', 'Managed by NEXORA account. Gateway stores an organization ID, member roles and member emails.', 'Until the organization or the account is deleted'],
  ['Billing records', 'Held by our payment provider (Stripe) as required for accounting. Gateway keeps only Stripe reference IDs.', 'As required by accounting law'],
]
export default function DataHandling() {
  return <MarketingShell><Section>
    <h1 className="max-w-3xl text-[40px] font-bold leading-[44px] tracking-tight">Data handling</h1>
    <p className="mt-4 max-w-prose text-text-muted">What Gateway stores, in plain words. Your prompts do pass through our servers on their way to your model provider; we do not keep them. The provider's own retention rules still apply to what they receive.</p>
    <div className="mt-12 overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm"><thead className="border-b border-border bg-surface"><tr>{['Data', 'What we keep', 'How long'].map(h => <th key={h} scope="col" className="px-4 py-3 text-left font-semibold">{h}</th>)}</tr></thead>
        <tbody className="divide-y divide-border">{rows.map(r => <tr key={r[0]}><td className="px-4 py-3 font-medium">{r[0]}</td><td className="px-4 py-3 text-text-muted">{r[1]}</td><td className="px-4 py-3 text-text-muted">{r[2]}</td></tr>)}</tbody></table>
    </div>
    <h2 className="mt-12 text-[28px] font-semibold leading-[34px]">Deleting your data</h2>
    <p className="mt-2 max-w-prose text-text-muted">An owner can delete the organization from Settings. That removes keys, logs, usage counts and members, and cancels the subscription first. If your NEXORA account or organization is deleted, Gateway removes the matching data automatically.</p>
    <h2 className="mt-12 text-[28px] font-semibold leading-[34px]">Processors</h2>
    <p className="mt-2 max-w-prose text-text-muted">This list will name every service that handles your data (hosting, database, payments, and your model provider) before general availability. It is a draft until then.</p>
  </Section></MarketingShell>
}
