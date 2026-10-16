import { expect, test } from './fixtures'

test('F05 revoke: the old key stops working immediately and stays listed as revoked', async ({ page, gateway }) => {
  const { secret } = await gateway.createKey('to-revoke')
  expect((await gateway.call(secret)).status()).toBe(200)

  await page.goto('/app/keys')
  page.once('dialog', d => { expect(d.message()).toContain('to-revoke'); d.accept() })
  await page.getByRole('button', { name: 'Revoke' }).click()
  await expect(page.getByText('Revoked')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Revoke' })).toHaveCount(0)

  const r = await gateway.call(secret)
  expect(r.status()).toBe(401)
  expect((await r.json()).error.code).toBe('invalid_key')
})

test('cancelling the revoke dialog keeps the key active', async ({ page, gateway }) => {
  const { secret } = await gateway.createKey('keep-me')
  await page.goto('/app/keys')
  page.once('dialog', d => d.dismiss())
  await page.getByRole('button', { name: 'Revoke' }).click()
  await expect(page.getByText('Active')).toBeVisible()
  expect((await gateway.call(secret)).status()).toBe(200)
})

test('rate limit: the third call in a minute on a 2/min key gets a 429 with Retry-After', async ({ request, dev }) => {
  const k = await (await request.post('http://localhost:8411/api/keys', { headers: dev, data: { name: 'slow', rpm_limit: 2 } })).json()
  const call = () => request.post('http://localhost:8411/v1/chat', { headers: { authorization: `Bearer ${k.secret}` }, data: { messages: [{ role: 'user', content: 'x' }] } })
  expect([(await call()).status(), (await call()).status()]).toEqual([200, 200])
  const r = await call()
  expect(r.status()).toBe(429)
  expect(Number(r.headers()['retry-after'])).toBeGreaterThan(0)
})
