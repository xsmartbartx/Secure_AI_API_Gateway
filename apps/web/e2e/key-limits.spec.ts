import AxeBuilder from '@axe-core/playwright'
import { expect, test } from './fixtures'

const API = 'http://localhost:8411'

test('create a key with limits, watch it fill up, hit the limit, then raise it', async ({ page, gateway }) => {
  await page.goto('/app/keys')
  await page.getByLabel('Key name').fill('capped')
  await page.getByText('Monthly limits (optional)').click()
  await page.getByLabel('Calls per month', { exact: true }).first().fill('2')
  await page.getByRole('button', { name: 'Create key' }).click()
  const banner = page.getByRole('alert').filter({ hasText: "You won't see it again" })
  const secret = (await banner.locator('code').innerText()).trim()
  await banner.getByLabel('I stored it somewhere safe').check()
  await banner.getByRole('button', { name: 'Done' }).click()

  const row = page.getByRole('row').filter({ hasText: 'capped' })
  await expect(row).toContainText('0 / 2 calls')
  expect((await gateway.call(secret)).status()).toBe(200)
  expect((await gateway.call(secret)).status()).toBe(200)
  const limited = await gateway.call(secret)
  expect(limited.status()).toBe(429)
  expect((await limited.json()).error.code).toBe('key_limit_reached')

  await page.reload()
  await expect(row).toContainText('2 / 2 calls')
  await expect(row).toContainText('Limit reached')
  expect((await new AxeBuilder({ page }).analyze()).violations.map(v => `${v.impact} ${v.id} ${v.nodes[0]?.target.join(' ')}`)).toEqual([])

  await row.getByRole('button', { name: 'Limits' }).click()
  const editor = page.getByRole('form', { name: 'Monthly limits for capped' })
  await editor.getByLabel('Calls per month').fill('10')
  await editor.getByLabel('Tokens per month').fill('5000')
  await editor.getByRole('button', { name: 'Save limits' }).click()
  await expect(row).toContainText('2 / 10 calls')
  await expect(row).toContainText('/ 5,000 tokens')
  expect((await gateway.call(secret)).status()).toBe(200)

  await row.getByRole('button', { name: 'Limits' }).click()           // clearing: blank means no limit
  await editor.getByLabel('Calls per month').fill('')
  await editor.getByLabel('Tokens per month').fill('')
  await editor.getByRole('button', { name: 'Save limits' }).click()
  await expect(row).not.toContainText('/ 10')
  await expect(row).toContainText('3 calls')
})

test('a limit below 1 is stopped in the form and nothing is sent', async ({ page, gateway, dev, request }) => {
  await gateway.createKey('plain')
  await page.goto('/app/keys')
  await page.getByRole('button', { name: 'Limits' }).click()
  const editor = page.getByRole('form', { name: 'Monthly limits for plain' })
  const calls = editor.getByLabel('Calls per month')
  await calls.fill('0')
  await editor.getByRole('button', { name: 'Save limits' }).click()
  expect(await calls.evaluate((el: HTMLInputElement) => el.validity.rangeUnderflow)).toBe(true)   // the browser's own validation message shows
  await expect(editor).toBeVisible()                                                              // still open: nothing was submitted
  const keys = (await (await request.get('http://localhost:8411/api/keys', { headers: dev })).json()).items
  expect(keys[0].monthly_call_limit).toBeNull()
})

test('developers see their keys usage but cannot change limits', async ({ page, request, org }) => {
  await request.get(`${API}/api/me`, { headers: { 'x-dev-org': org, 'x-dev-user': 'founder' } })
  await request.post(`${API}/api/keys`, { headers: { 'x-dev-org': org, 'x-dev-user': 'founder' }, data: { name: 'team-key', monthly_call_limit: 5 } })
  await page.addInitScript(() => localStorage.setItem('devRole', 'developer'))
  await page.goto('/app/keys')
  await expect(page.getByRole('row').filter({ hasText: 'team-key' })).toContainText('0 / 5 calls')
  await expect(page.getByRole('button', { name: 'Limits' })).toHaveCount(0)
})

test('the dashboard warns at 80% of the monthly quota and says so plainly at 100%', async ({ page, request, dev }) => {
  // quota is 100 calls on the free plan: use a key with a high rate limit
  const k = await (await request.post(`${API}/api/keys`, { headers: dev, data: { name: 'bulk', rpm_limit: 1000 } })).json()
  const call = () => request.post(`${API}/v1/chat`, { headers: { authorization: `Bearer ${k.secret}` }, data: { messages: [{ role: 'user', content: 'x' }] } })
  await page.goto('/app')
  await expect(page.getByRole('status').filter({ hasText: 'of 100 calls this month' })).toHaveCount(0)   // quiet while there is room

  for (let i = 0; i < 80; i++) expect((await call()).status()).toBe(200)
  await page.reload()
  const warn = page.getByRole('status').filter({ hasText: 'You have used 80 of 100 calls this month.' })
  await expect(warn).toBeVisible()
  await expect(warn.getByRole('link', { name: 'See your plan' })).toHaveAttribute('href', '/app/billing')

  for (let i = 0; i < 20; i++) await call()
  await page.reload()
  await expect(page.getByRole('status').filter({ hasText: 'You have used all 100 calls this month.' })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations.map(v => `${v.impact} ${v.id}`)).toEqual([])
})
