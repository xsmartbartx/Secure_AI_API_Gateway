import Link from 'next/link'
import { ReactNode } from 'react'

export function MarketingShell({ children }: { children: ReactNode }) {
  return <>
    <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:bg-bg focus:p-2">Skip to content</a>
    <header className="sticky top-0 z-10 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-12 max-w-marketing items-center justify-between px-4">
        <Link href="/" className="font-semibold tracking-tight">NEXORA <span className="font-normal text-text-muted">Gateway</span></Link>
        <nav aria-label="Primary" className="flex items-center gap-5 text-sm">
          <Link href="/security" className="text-text-muted hover:text-text">Security</Link>
          <Link href="/pricing" className="text-text-muted hover:text-text">Pricing</Link>
          <a href="https://docs.onenexora.com/products" className="hidden text-text-muted hover:text-text sm:inline">Docs</a>
          <Link href="/app" className="rounded-md bg-accent px-3 py-1.5 font-semibold text-on-accent hover:bg-accent-hover">Open Gateway</Link>
        </nav>
      </div>
    </header>
    <main id="main">{children}</main>
    <footer className="border-t border-border bg-surface">
      <div className="mx-auto flex max-w-marketing flex-wrap items-center justify-between gap-4 px-4 py-8 text-sm text-text-muted">
        <span>© NEXORA. Gateway is in beta.</span>
        <nav aria-label="Footer" className="flex flex-wrap gap-5">
          <a href="https://onenexora.com">NEXORA</a><a href="https://docs.onenexora.com">Docs</a><a href="https://status.onenexora.com">Status</a>
          <Link href="/data-handling">Data handling</Link><Link href="/terms">Terms</Link><Link href="/privacy">Privacy</Link>
        </nav>
      </div>
    </footer>
  </>
}

export const Section = ({ children, className = '' }: { children: ReactNode; className?: string }) =>
  <section className={`mx-auto max-w-marketing px-4 py-24 ${className}`}>{children}</section>
