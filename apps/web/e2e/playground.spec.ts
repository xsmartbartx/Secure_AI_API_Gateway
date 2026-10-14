import { expect, test } from './fixtures'

test('playground streams the answer and the call shows up in the logs', async ({ page }) => {
  await page.goto('/app/playground')
  await expect(page.getByText('Your response will appear here.')).toBeVisible()
  await page.getByLabel('Message').fill('one two three four five six seven eight nine ten eleven twelve')
  await page.getByRole('button', { name: 'Send' }).click()

  const out = page.locator('p.whitespace-pre-wrap')
  await expect(out).toContainText('[mock] one')        // first words arrive...
  await expect(out).not.toContainText('twelve')        // ...before the last ones (the mock emits a word every 150 ms; polling backs off, so keep the stream long)
  await expect(out).toContainText('eleven twelve')
  await expect(page.getByText(/tokens · mock-1/)).toBeVisible()

  await page.getByRole('link', { name: 'Logs' }).click()
  await expect(page.getByRole('row').filter({ hasText: 'mock-1' }).getByText('Allowed')).toBeVisible()
})

test('Stop cancels the stream; the call is logged as cancelled by the client', async ({ page }) => {
  await page.goto('/app/playground')
  await page.getByLabel('Message').fill('a b c d e f g h i j k l m n o p')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.locator('p.whitespace-pre-wrap')).toContainText('[mock] a')
  await page.getByRole('button', { name: 'Stop' }).click()
  await expect(page.getByText('Stopped')).toBeVisible()
  await expect(page.locator('p.whitespace-pre-wrap')).not.toContainText(' p')

  await page.getByRole('link', { name: 'Logs' }).click()
  await expect(page.getByText('499 · cancelled by client')).toBeVisible()
})

test('playground shows a readable message when the monthly quota is used up', async ({ page, request, dev }) => {
  const k = await (await request.post('http://localhost:8411/api/keys', { headers: dev, data: { name: 'bulk', rpm_limit: 1000 } })).json()
  for (let i = 0; i < 100; i++) {
    const r = await request.post('http://localhost:8411/v1/chat', { headers: { authorization: `Bearer ${k.secret}` }, data: { messages: [{ role: 'user', content: 'x' }] } })
    expect(r.status()).toBe(200)
  }
  await page.goto('/app/billing')
  await expect(page.getByText('100 / 100')).toBeVisible()
  await expect(page.getByText("You have used 100% of this month's calls.")).toBeVisible()

  await page.goto('/app/playground')
  await page.getByLabel('Message').fill('one more')
  await page.getByRole('button', { name: 'Send' }).click()
  await expect(page.locator('p[role=alert]')).toContainText('Monthly call quota reached')
})
