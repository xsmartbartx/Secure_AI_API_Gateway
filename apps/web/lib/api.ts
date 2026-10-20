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
  if (process.env.NEXT_PUBLIC_DEV_AUTH === '1') {
    // dev only: a localStorage override lets tests run each case in its own organization
    let org = 'org_demo', role = ''
    try { org = localStorage.getItem('devOrg') || org; role = localStorage.getItem('devRole') || '' } catch {}
    return { 'x-dev-org': org, 'x-dev-user': 'demo', ...(role ? { 'x-dev-role': role } : {}) }
  }
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
export type Key = { id: string; name: string; prefix: string; last4: string; rpm_limit: number; monthly_call_limit: number | null; monthly_token_limit: number | null; month_calls: number; month_tokens: number; created_at: string; last_used_at: string | null; revoked_at: string | null }
export type Log = { id: string; request_id: string; ts: string; key_id: string | null; provider: string | null; model: string | null; status_code: number; decision: 'allow' | 'flag' | 'block' | 'error' | 'pending'; risk_score: number | null; tokens_in: number; tokens_out: number; latency_ms: number | null }

/** The `data:` payload of every server-sent event in a response body, as it arrives. */
async function* sseData(body: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) return
    buf += decoder.decode(value, { stream: true })
    let end: number
    while ((end = buf.indexOf('\n\n')) >= 0) {
      const event = buf.slice(0, end).trim()
      buf = buf.slice(end + 2)
      if (event.startsWith('data:')) yield event.slice(5).trim()
    }
  }
}

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
  let usage: { total_tokens: number } | null = null
  let model = ''
  for await (const data of sseData(res.body)) {
    if (data === '[DONE]') return { usage, model }
    const chunk = JSON.parse(data)
    if (chunk.error) throw new ApiError(502, chunk.error.code, chunk.error.message)
    model = chunk.model ?? model
    const text = chunk.choices?.[0]?.delta?.content
    if (text) onDelta(text)
    usage = chunk.usage ?? usage
  }
  throw new ApiError(502, 'stream_interrupted', 'The response was cut off before it finished. Try again.')  // the stream ended without [DONE]
}

/** Download an authenticated endpoint (e.g. CSV) through a temporary link. */
export async function apiDownload(path: string, fallbackName: string) {
  const res = await fetch(`${API_BASE}${path}`, { headers: await authHeaders(), cache: 'no-store' })
  if (!res.ok) {
    const b = await res.json().catch(() => ({}))
    throw new ApiError(res.status, b?.error?.code ?? 'error', b?.error?.message ?? res.statusText)
  }
  const name = /filename="([^"]+)"/.exec(res.headers.get('content-disposition') ?? '')?.[1] ?? fallbackName
  const url = URL.createObjectURL(await res.blob())
  const a = Object.assign(document.createElement('a'), { href: url, download: name })
  a.click()
  URL.revokeObjectURL(url)
}

export type UsageRow = { id: string | null; label: string; prefix?: string | null; revoked?: boolean; calls: number; blocked: number; errors: number; tokens_in: number; tokens_out: number }
export type Usage = { from: string; to: string; group: 'key' | 'model' | 'day'; rows: UsageRow[]; totals: Omit<UsageRow, 'id' | 'label'> }
