'use client'
import { ReactNode } from 'react'

export type Mode = 'off' | 'monitor' | 'enforce'

export type ModeOption = { value: Mode; label: string; help: string }

/** Radio group for a policy's mode. Wrapped in a fieldset so it reads as one control to assistive technology. */
export function ModeFieldset({ name, value, onChange, options, disabled }: Readonly<{ name: string; value: Mode; onChange: (m: Mode) => void; options: ModeOption[]; disabled: boolean }>) {
  return <fieldset disabled={disabled} className="space-y-2">
    <legend className="mb-1 text-sm font-medium">Mode</legend>
    {options.map(o => <label key={o.value} className="flex cursor-pointer items-start gap-3 rounded-md border border-border p-3 has-[:checked]:border-accent has-[:checked]:bg-accent-subtle">
      <input type="radio" name={name} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} className="mt-1" />
      <span><span className="block font-medium">{o.label}</span><span className="block text-sm text-text-muted">{o.help}</span></span></label>)}
  </fieldset>
}

export function SaveRow({ canEdit, busy, dirty, msg }: Readonly<{ canEdit: boolean; busy: boolean; dirty: boolean; msg: { ok: boolean; text: string } | null }>): ReactNode {
  if (!canEdit) return <p className="text-sm text-text-muted">Only admins and owners can change policies.</p>
  return <div className="flex flex-wrap items-center gap-3">
    <button type="submit" disabled={busy || !dirty} className="inline-flex h-10 items-center justify-center rounded-md bg-accent px-4 text-sm font-semibold text-on-accent hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50">{busy ? 'Saving…' : 'Save policy'}</button>
    {msg?.ok && <output className="text-sm text-success">{msg.text}</output>}
    {msg && !msg.ok && <p role="alert" className="text-sm text-danger">{msg.text}</p>}
  </div>
}
