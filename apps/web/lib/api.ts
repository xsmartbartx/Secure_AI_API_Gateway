// Single data layer for the dashboard. Dev: sends X-Dev-* headers. Prod: sends the NEXORA account session token.
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8000'

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message) }
}

function authHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {}
  const token = (window as any).__NEXORA_SESSION_TOKEN__ as string | undefined
  if (token) return { authorization: `Bearer ${token}` }
  if (process.env.NEXT_PUBLIC_DEV_AUTH === '1') return { 'x-dev-org': 'org_demo', 'x-dev-user': 'demo' }
  return {}
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { 'content-type': 'application/json', ...authHeaders(), ...(init.headers as object) },
    cache: 'no-store',
  })
  const body = await res.json().catch(() => ({}))
  if (!res.ok) throw new ApiError(res.status, body?.error?.code ?? 'error', body?.error?.message ?? res.statusText)
  return body as T
}

export type Overview = { calls: number; blocked: number; errors: number; tokens: number; p50_latency_ms: number | null; quota: { used: number; limit: number }; series: { day: string; calls: number; blocked: number; errors: number }[] }
export type Key = { id: string; name: string; prefix: string; last4: string; rpm_limit: number; created_at: string; last_used_at: string | null; revoked_at: string | null }
export type Log = { id: string; request_id: string; ts: string; key_id: string | null; provider: string | null; model: string | null; status_code: number; decision: 'allow' | 'flag' | 'block' | 'error'; risk_score: number | null; tokens_in: number; tokens_out: number; latency_ms: number | null }
