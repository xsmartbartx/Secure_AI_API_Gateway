'use client'
import { Activity, BarChart3, CreditCard, KeyRound, LayoutDashboard, ListTree, Menu, Moon, Plug, ScrollText, Settings, ShieldAlert, Sun, Users, X } from 'lucide-react'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { useApi } from '@/lib/use-fetch'
import { api, apiDownload } from '@/lib/api'
import { AuthGate, useSession } from '@/lib/session'

const NAV = [
  { href: '/app', label: 'Overview', icon: LayoutDashboard },
  { href: '/app/playground', label: 'Playground', icon: Activity },
  { href: '/app/keys', label: 'API keys', icon: KeyRound },
  { href: '/app/logs', label: 'Logs', icon: ScrollText },
  { href: '/app/usage', label: 'Usage', icon: BarChart3 },
  { href: '/app/security', label: 'Security', icon: ShieldAlert },
  { href: '/app/providers', label: 'Providers', icon: Plug },
  { href: '/app/policies', label: 'Policies', icon: ListTree },
  { href: '/app/team', label: 'Team', icon: Users },
  { href: '/app/billing', label: 'Billing', icon: CreditCard },
  { href: '/app/settings', label: 'Settings', icon: Settings },
]

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return <AuthGate><AppShell>{children}</AppShell></AuthGate>
}

function AppShell({ children }: { children: React.ReactNode }) {
  const session = useSession()
  const path = usePathname()
  const [open, setOpen] = useState(false)
  const [dark, setDark] = useState(false)
  const { data: me } = useApi<{ org: { name: string; plan: string }; member: { email: string; role: string; status: string } }>('/api/me')
  useEffect(() => { try { const t = localStorage.getItem('theme'); if (t) setDark(t === 'dark') } catch {} }, [])
  useEffect(() => { document.documentElement.dataset.theme = dark ? 'dark' : 'light'; try { localStorage.setItem('theme', dark ? 'dark' : 'light') } catch {} }, [dark])
  useEffect(() => setOpen(false), [path])
  const current = NAV.find(n => n.href === path)?.label ?? 'Overview'

  return <div className="min-h-screen">
    <a href="#content" className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:bg-bg focus:p-2">Skip to content</a>
    <header className="fixed inset-x-0 top-0 z-20 flex h-12 items-center gap-3 border-b border-border bg-bg px-3">
      <button className="rounded p-2 lg:hidden" aria-label={open ? 'Close menu' : 'Open menu'} aria-expanded={open} onClick={() => setOpen(!open)}>{open ? <X size={18} /> : <Menu size={18} />}</button>
      <Link href="/" className="font-semibold tracking-tight">NEXORA <span className="font-normal text-text-muted">Gateway</span></Link>
      <span className="mx-2 hidden h-5 w-px bg-border sm:block" />
      <span className="hidden truncate text-text-muted sm:block">{me?.org.name ?? ''}</span>
      <div className="ml-auto flex items-center gap-2">
        <span className="hidden text-xs text-text-muted md:block">{session.email || me?.member.email}</span>
        <button className="rounded p-2 hover:bg-surface" aria-label="Toggle theme" onClick={() => setDark(!dark)}>{dark ? <Sun size={16} /> : <Moon size={16} />}</button>
        {process.env.NEXT_PUBLIC_DEV_AUTH !== '1' && <button className="rounded px-2 py-1 text-xs hover:bg-surface" onClick={session.signOut}>Sign out</button>}
      </div>
    </header>
    <nav aria-label="Dashboard" className={`fixed bottom-0 left-0 top-12 z-10 w-60 overflow-y-auto bg-nav-bg p-2 transition-transform lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
      <ul className="space-y-0.5">{NAV.map(n => { const active = path === n.href; return <li key={n.href}>
        <Link href={n.href} aria-current={active ? 'page' : undefined} className={`flex h-9 items-center gap-3 rounded-md px-3 text-sm ${active ? 'bg-white/10 font-semibold text-nav-active' : 'text-nav-text hover:bg-white/5 hover:text-nav-active'}`}><n.icon size={16} aria-hidden />{n.label}</Link></li> })}</ul>
      <p className="mt-6 px-3 text-xs text-nav-text">Plan: {me?.org.plan ?? '…'}</p>
    </nav>
    <main id="content" className="px-4 pb-16 pt-[72px] lg:pl-[272px]">
      <div className="mx-auto max-w-content">
        <p className="mb-4 text-xs text-text-muted">Gateway / {current}</p>
        {me?.member.status === 'suspended' ? <Suspended onSignOut={session.signOut} /> : children}
      </div>
    </main>
  </div>
}

// A suspended member still gets to see why, take their own data, and leave.
function Suspended({ onSignOut }: { onSignOut: () => void }) {
  const [err, setErr] = useState<string | null>(null)
  async function leave() {
    if (!confirm('Leave this organization? Your membership record is deleted.')) return
    try { await api('/api/me', { method: 'DELETE' }); onSignOut(); window.location.href = '/' } catch (e: any) { setErr(e.message) }
  }
  return <div className="mx-auto max-w-lg rounded-lg border border-border bg-surface-raised p-8 text-center shadow-card">
    <h1 className="text-xl font-semibold">Your access is suspended</h1>
    <p className="mt-2 text-text-muted">An owner of this organization suspended your access to Gateway. Ask them to restore it. You can still download your own data or leave the organization.</p>
    <div className="mt-6 flex flex-wrap justify-center gap-3">
      <button className="h-10 rounded-md border border-border-input px-4 text-sm font-semibold hover:bg-surface" onClick={() => apiDownload('/api/me/export', 'my-gateway-data.json').catch(e => setErr(e.message))}>Download my data</button>
      <button className="h-10 rounded-md border border-border-input px-4 text-sm font-semibold hover:bg-surface" onClick={leave}>Leave organization</button>
      <button className="h-10 rounded-md px-4 text-sm font-semibold hover:bg-surface" onClick={onSignOut}>Sign out</button>
    </div>
    {err && <p role="alert" className="mt-4 text-sm text-danger">{err}</p>}
  </div>
}
