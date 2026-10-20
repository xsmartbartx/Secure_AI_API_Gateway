type Day = { day: string; calls: number; blocked: number }

export function BarSeries({ data, label }: Readonly<{ data: Day[]; label: string }>) {
  const max = Math.max(1, ...data.map(d => d.calls))
  const w = 100 / Math.max(7, data.length)
  return <figure>
    <svg viewBox="0 0 100 40" className="h-40 w-full" role="img" aria-label={label} preserveAspectRatio="none">
      {data.map((d, i) => <g key={d.day}><title>{`${d.day}: ${d.calls} calls, ${d.blocked} blocked`}</title>
        <rect x={i * w + w * 0.15} y={40 - (d.calls / max) * 38} width={w * 0.7} height={(d.calls / max) * 38} fill="var(--color-accent)" rx="0.5" />
        {d.blocked > 0 && <rect x={i * w + w * 0.15} y={40 - (d.blocked / max) * 38} width={w * 0.7} height={(d.blocked / max) * 38} fill="var(--color-danger)" rx="0.5" />}</g>)}
    </svg>
    <figcaption className="mt-2 flex justify-between text-xs text-text-muted"><span>{data[0]?.day}</span><span>{data.at(-1)?.day}</span></figcaption>
  </figure>
}
