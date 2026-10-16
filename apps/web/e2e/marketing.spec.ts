import { expect, test } from './fixtures'

test('home explains the product and leads to the dashboard', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Install nothing')
  await expect(page.getByText('curl https://api.onenexora.com/v1/chat')).toBeVisible()
  await expect(page.getByRole('heading', { name: 'What is real today' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'On the roadmap' })).toBeVisible()
  await page.getByRole('link', { name: 'Open Gateway' }).first().click()
  await expect(page).toHaveURL(/\/app$/)
})

test('pricing shows the live plans and the FAQ', async ({ page }) => {
  await page.goto('/pricing')
  await expect(page.getByRole('heading', { name: 'Free' })).toBeVisible()
  await expect(page.getByText('100 calls / month')).toBeVisible()
  await expect(page.getByText('1,500 calls / month')).toBeVisible()
  await expect(page.getByText('Do you store my prompts?')).toBeVisible()
})

test('security and data-handling pages state what is stored', async ({ page }) => {
  await page.goto('/security')
  await expect(page.getByRole('heading', { name: 'Live' })).toBeVisible()
  await page.goto('/data-handling')
  await expect(page.getByRole('row', { name: /Prompts and responses/ })).toContainText('Not stored')
  await expect(page.getByRole('heading', { name: 'Deleting your data' })).toBeVisible()
})

test('footer links work and there are no dead internal links', async ({ page, request }) => {
  await page.goto('/')
  const hrefs = await page.locator('a[href^="/"]').evaluateAll(as => [...new Set(as.map(a => (a as HTMLAnchorElement).getAttribute('href')!))])
  for (const h of hrefs) expect((await request.get(h)).status(), h).toBe(200)
})

test('unknown routes give a 404 page, not a crash', async ({ request }) => {
  const r = await request.get('/nope')
  expect(r.status()).toBe(404)
  expect(await r.text()).toContain('could not be found')
})

test('the favicon is served', async ({ request }) => {
  expect((await request.get('/icon.svg')).status()).toBe(200)
})
