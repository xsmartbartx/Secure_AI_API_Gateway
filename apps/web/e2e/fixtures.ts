import { APIRequestContext, expect, Page, test as base } from '@playwright/test'

export const API = 'http://localhost:8411'
let n = 0

type Fixtures = { org: string; dev: Record<string, string>; gateway: Gateway }

export class Gateway {
  constructor(private request: APIRequestContext, private dev: Record<string, string>) {}
  async createKey(name = 'e2e-key') {
    const r = await this.request.post(`${API}/api/keys`, { headers: this.dev, data: { name } })
    expect(r.status()).toBe(201)
    return (await r.json()) as { id: string; secret: string }
  }
  async call(secret: string, content = 'hello from e2e', extra: object = {}) {
    return this.request.post(`${API}/v1/chat`, { headers: { authorization: `Bearer ${secret}` }, data: { messages: [{ role: 'user', content }], ...extra } })
  }
}

// Every test gets its own organization (and so its own keys, logs and quota) and fails on console errors or 5xx responses.
export const test = base.extend<Fixtures>({
  org: async ({}, use, info) => { await use(`org_e2e_${Date.now()}_${info.workerIndex}_${n++}`) },
  dev: async ({ org }, use) => { await use({ 'x-dev-org': org, 'x-dev-user': 'demo' }) },
  gateway: async ({ request, dev }, use) => { await use(new Gateway(request, dev)) },
  page: async ({ page, org }, use) => {
    const problems: string[] = []
    await page.addInitScript(o => { try { localStorage.setItem('devOrg', o) } catch {} }, org)
    // 4xx answers the app handles on purpose (validation, auth, quota) are asserted by the tests themselves; a 404 is never expected
    page.on('console', m => { if (m.type() === 'error' && !/status of (401|403|409|422|429)/.test(m.text())) problems.push(`console: ${m.text()}`) })
    page.on('pageerror', e => problems.push(`pageerror: ${e.message}`))
    page.on('response', r => { if (r.status() >= 500) problems.push(`${r.status()} ${r.url()}`) })
    await use(page)
    expect(problems, 'console errors or 5xx responses during the test').toEqual([])
  },
})
export { expect }
export type { Page }
