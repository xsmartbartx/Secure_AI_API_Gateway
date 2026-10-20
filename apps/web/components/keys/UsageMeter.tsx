import { Meter } from '@/components/ui'

const n = (v: number) => v.toLocaleString()

/** This month's use of one counter, against an optional limit. Text first; the bar is a visual extra with its own label. */
export function UsageMeter({ label, used, limit }: Readonly<{ label: string; used: number; limit: number | null }>) {
  if (!limit) return <p className="text-xs text-text-muted">{n(used)} {label} <span className="sr-only">(no limit)</span></p>
  const pct = Math.min(100, Math.round((used / limit) * 100))
  return <div className="min-w-36">
    <p className="text-xs">{n(used)} / {n(limit)} {label}{pct >= 100 && <span className="ml-1 font-medium text-danger">Limit reached</span>}</p>
    <Meter pct={pct} label={`${label} used this month`} className="mt-1" />
  </div>
}
