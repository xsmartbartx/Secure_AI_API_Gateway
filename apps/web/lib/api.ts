// Single data layer for the dashboard. Prod: Bearer session token from the NEXORA account (see lib/session.tsx). Dev only: X-Dev-* headers.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message) }
}

let tokenGetter: (() => Promise<string | null>) | null = null
export function setTokenGetter(fn: (() => Promise<string | null>) | null) { tokenGetter = fn }

async function authHeaders(): Promise<Record<string, string>> {
  if (tokenGetter) {
    const token = await tokenGetter()
    if (token) return { authorization: `Bearer ${token}` }
  }
  if (process.env.NEXT_PUBLIC_DEV_AUTH === '1') return { 'x-dev-org': 'org_demo', 'x-dev-user': 'demo' }
  return {}
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...(await authHeaders()), ...(init.headers as object) },
    cache: 'no-store',
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, body?.error?.code ?? 'error', body?.error?.message ?? res.statusText)
  return body as T
}

export type Overview = { calls: number; blocked: number; errors: number; tokens: number; p50_latency_ms: number | null; quota: { used: number; limit: number }; series: { day: string; calls: number; blocked: number; errors: number }[] }
export type Key = { id: string; name: string; prefix: string; last4: string; rpm_limit: number; created_at: string; last_used_at: string | null; revoked_at: string | null }
export type Log = { id: string; request_id: string; ts: string; key_id: string | null; provider: string | null; model: string | null; status_code: number; decision: 'allow' | 'flag' | 'block' | 'error'; risk_score: number | null; tokens_in: number; tokens_out: number; latency_ms: number | null }

/** POST that answers with an SSE stream of chat chunks. Calls onDelta for each text piece; resolves with the final usage. */
export async function apiStream(path: string, body: unknown, onDelta: (t: string) => void, signal?: AbortSignal) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST', body: JSON.stringify(body), signal, cache: 'no-store',
    headers: { 'content-type': 'application/json', ...(await authHeaders()) },
  })
  if (!res.ok || !res.body) {
    const b = await res.json().catch(() => ({}))
    throw new ApiError(res.status, b?.error?.code ?? 'error', b?.error?.message ?? res.statusText)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = '', usage: { total_tokens: number } | null = null, model = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let i: number
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const line = buf.slice(0, i).trim(); buf = buf.slice(i + 2)
      if (!line.startsWith('data:')) continue
      const data = line.slice(5).trim()
      if (data === '[DONE]') return { usage, model }
      const obj = JSON.parse(data)
      if (obj.error) throw new ApiError(502, obj.error.code, obj.error.message)
      model = obj.model ?? model
      const t = obj.choices?.[0]?.delta?.content
      if (t) onDelta(t)
      if (obj.usage) usage = obj.usage
    }
  }
  return { usage, model }
}
