'use client'
import { AlertTriangle, Check, CircleDashed, Copy, Inbox, ShieldX, X } from 'lucide-react'
import { ButtonHTMLAttributes, ReactNode, useState } from 'react'

const cx = (...a: (string | false | undefined)[]) => a.filter(Boolean).join(' ')

export function Button({ variant = 'primary', size = 'md', loading, className, children, ...p }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'ghost' | 'danger'; size?: 'sm' | 'md' | 'lg'; loading?: boolean }) {
  const v = { primary: 'bg-accent text-on-accent hover:bg-accent-hover', secondary: 'border border-border-input bg-bg text-text hover:bg-surface', ghost: 'text-text hover:bg-surface', danger: 'bg-danger text-bg hover:opacity-90' }[variant]
  const s = { sm: 'h-8 px-3 text-sm', md: 'h-10 px-4 text-sm', lg: 'h-12 px-6 text-base' }[size]
  return <button {...p} aria-busy={loading || undefined} disabled={p.disabled || loading}
    className={cx('inline-flex items-center justify-center gap-2 rounded-md font-semibold transition-colors disabled:opacity-50 disabled:cursor-not-allowed', v, s, className)}>
    {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden />}{children}</button>
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cx('rounded-lg border border-border bg-surface-raised shadow-card', className)}>{children}</div>
}

export function PageHeader({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
    <div><h1 className="text-[28px] leading-[34px] font-semibold">{title}</h1>{description && <p className="mt-1 text-text-muted">{description}</p>}</div>{action}</div>
}

export function Pill({ decision }: { decision: 'allow' | 'flag' | 'block' | 'error' | 'pending' }) {
  const m = { allow: ['bg-success-subtle text-success', Check, 'Allowed'], flag: ['bg-warning-subtle text-warning', AlertTriangle, 'Flagged'], block: ['bg-danger-subtle text-danger', ShieldX, 'Blocked'], error: ['bg-surface text-text-muted', X, 'Error'], pending: ['bg-surface text-text-muted', CircleDashed, 'In progress'] } as const
  const [c, Icon, label] = m[decision]
  return <span className={cx('inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium', c)}><Icon size={12} aria-hidden />{label}</span>
}

export function Empty({ title, help, action }: { title: string; help: string; action?: ReactNode }) {
  return <div className="flex flex-col items-center gap-2 px-6 py-16 text-center"><Inbox className="text-text-muted" aria-hidden /><p className="text-base font-semibold">{title}</p><p className="max-w-sm text-text-muted">{help}</p>{action}</div>
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return <div role="alert" className="flex flex-col items-center gap-3 px-6 py-12 text-center"><AlertTriangle className="text-danger" aria-hidden /><p>{message}</p>{onRetry && <Button variant="secondary" size="sm" onClick={onRetry}>Try again</Button>}</div>
}

export function Skeleton({ className }: { className?: string }) { return <div aria-hidden className={cx('skeleton h-4', className)} /> }

export function CodeBlock({ code, label }: { code: string; label?: string }) {
  const [done, setDone] = useState(false)
  return <div className="relative overflow-hidden rounded-md border border-border bg-nav-bg text-nav-text">
    {label && <div className="border-b border-border/30 px-4 py-2 text-xs text-nav-text">{label}</div>}
    <pre className="overflow-x-auto p-4 font-mono text-[13px] leading-5"><code>{code}</code></pre>
    <button aria-label="Copy code" onClick={async () => { try { await navigator.clipboard?.writeText(code); setDone(true); setTimeout(() => setDone(false), 1500) } catch { /* clipboard blocked: nothing to confirm */ } }}
      className="absolute right-2 top-2 rounded p-2 text-nav-text hover:text-nav-active">{done ? <Check size={16} /> : <Copy size={16} />}</button></div>
}

export function Th({ children }: { children: ReactNode }) { return <th scope="col" className="px-4 py-2 text-left text-xs font-semibold uppercase tracking-wide text-text-muted">{children}</th> }
export const Td = ({ children, className }: { children: ReactNode; className?: string }) => <td className={cx('px-4 py-3', className)}>{children}</td>
