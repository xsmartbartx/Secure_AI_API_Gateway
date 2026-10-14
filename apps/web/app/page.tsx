import Link from 'next/link'
import { CodeBlock } from '@/components/ui'
import { MarketingShell, Section } from '@/components/marketing'

const sample = `curl https://api.onenexora.com/v1/chat \\
  -H "Authorization: Bearer nx_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"messages":[{"role":"user","content":"Hello"}]}'`

export default function Home() {
  return <MarketingShell>
    <Section className="pb-12 pt-28 text-center">
      <p className="mb-4 text-sm font-medium text-accent">Beta</p>
      <h1 className="mx-auto max-w-3xl text-[44px] font-bold leading-[1.05] tracking-tight sm:text-[64px] sm:leading-[68px]">Govern every model call. Install nothing.</h1>
      <p className="mx-auto mt-6 max-w-prose text-base text-text-muted sm:text-lg">NEXORA Gateway is a hosted door in front of your model provider. Your apps call one endpoint with one key. Every request is authenticated, limited, and logged, and there is no package to install, patch, or trust inside your own stack.</p>
      <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
        <Link href="/app" className="inline-flex h-12 items-center rounded-md bg-accent px-6 text-base font-semibold text-on-accent hover:bg-accent-hover">Open Gateway</Link>
        <a href="https://docs.onenexora.com/products" className="text-base font-semibold text-accent">Read the quickstart →</a>
      </div>
    </Section>
    <Section className="pt-0"><div className="mx-auto max-w-prose"><CodeBlock label="Your first governed call" code={sample} /></div></Section>
    <Section className="pt-0">
      <h2 className="text-[28px] font-semibold leading-[34px]">Why a hosted gateway</h2>
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div><h3 className="font-semibold">Self-hosted gateways become part of your attack surface.</h3><p className="mt-2 text-text-muted">An open-source proxy you run holds your provider keys and sees every prompt. When one of its releases is compromised, so is everything that trusted it. With Gateway there is nothing of ours inside your build.</p></div>
        <div><h3 className="font-semibold">You can't govern what you can't see.</h3><p className="mt-2 text-text-muted">Teams share provider keys and have no record of who sent what. Gateway gives every app its own key, limits, and an audit log, so you can see usage and shut a key off in one click.</p></div>
      </div>
    </Section>
    <Section>
      <h2 className="mb-12 text-center text-[40px] font-bold leading-[44px] tracking-tight">Key. Call. Govern.</h2>
      <ol className="grid gap-8 md:grid-cols-3">
        {[['Key', 'Create a Gateway key in the dashboard. It is shown once and stored only as a hash.'], ['Call', 'Send a chat request to one endpoint. Same shape whichever provider sits behind it.'], ['Govern', 'Every call is authenticated, rate limited, checked against your quota, and written to your audit log.']].map(([t, d], i) =>
          <li key={t} className="rounded-lg border border-border bg-surface-raised p-6 shadow-card"><span className="text-sm text-text-muted">0{i + 1}</span><h3 className="mt-2 text-xl font-semibold">{t}</h3><p className="mt-2 text-text-muted">{d}</p></li>)}
      </ol>
    </Section>
    <Section className="bg-surface">
      <h2 className="text-[28px] font-semibold leading-[34px]">What is real today</h2>
      <ul className="mt-6 grid gap-3 text-base md:grid-cols-2">
        {['One governed endpoint and one key in front of your provider', 'Authentication, rate limiting, and monthly quota on every call', 'Request logs with decision, latency, and token counts, and a prompt hash instead of prompt text', 'A playground to test prompts without a key'].map(x => <li key={x} className="flex gap-3"><span className="text-success" aria-hidden>✓</span>{x}</li>)}
      </ul>
      <h2 className="mt-12 text-[28px] font-semibold leading-[34px]">On the roadmap</h2>
      <ul className="mt-6 grid gap-3 text-base text-text-muted md:grid-cols-2">
        {['Multi-provider routing', 'Model allowlist and policy engine', 'Data loss prevention and prompt-injection detection', 'SIEM export and webhooks'].map(x => <li key={x} className="flex gap-3"><span aria-hidden>○</span>{x}</li>)}
      </ul>
    </Section>
    <Section>
      <h2 className="text-[28px] font-semibold leading-[34px]">Questions</h2>
      <dl className="mt-6 grid gap-6 md:grid-cols-2">
        {[['Do you store my prompts?', 'No. We store a hash of each prompt with the model, token counts, latency, and decision. See Data handling.'], ['Which providers can I use?', 'One configured upstream provider today. Multi-provider routing is on the roadmap.'], ['What does it cost?', 'Free and Starter plans are live. See Pricing.'], ['Does it stream?', 'Yes. Set stream to true and read the response as server-sent events.']].map(([q, a]) => <div key={q}><dt className="font-semibold">{q}</dt><dd className="mt-1 text-text-muted">{a}</dd></div>)}
      </dl>
    </Section>
    <Section className="text-center">
      <h2 className="text-[40px] font-bold leading-[44px] tracking-tight">Make your first call in minutes.</h2>
      <div className="mt-8"><Link href="/app" className="inline-flex h-12 items-center rounded-md bg-accent px-6 text-base font-semibold text-on-accent hover:bg-accent-hover">Open Gateway</Link></div>
    </Section>
  </MarketingShell>
}
