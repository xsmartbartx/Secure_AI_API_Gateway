import type { Metadata } from 'next'
import { MarketingShell, Section } from '@/components/marketing'
export const metadata: Metadata = { title: 'Terms' }
export default function Page() {
  return <MarketingShell><Section><h1 className="text-[40px] font-bold leading-[44px]">Terms</h1>
    <p className="mt-4 max-w-prose text-text-muted">This page is a draft and has not been reviewed by a lawyer. The final text will be published before general availability.</p></Section></MarketingShell>
}
