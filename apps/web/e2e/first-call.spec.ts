import { expect, test } from './fixtures'

// F01: sign in -> create a key -> make a call -> see it in the logs. Target: a handful of clicks.
test('F01 first call: empty overview, create key, call, see it logged', async ({ page, gateway }) => {
  await page.goto('/app')
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible()
  await expect(page.getByText('No calls yet')).toBeVisible()

  await page.getByRole('link', { name: 'Create your first key' }).click()
  await expect(page).toHaveURL(/\/app\/keys$/)
  await expect(page.getByText('No keys yet')).toBeVisible()

  await page.getByLabel('Key name').fill('production-backend')
  await page.getByRole('button', { name: 'Create key' }).click()

  const banner = page.getByRole('alert').filter({ hasText: "You won't see it again" })
  await expect(banner).toBeVisible()
  const secret = (await banner.locator('code').innerText()).trim()
  expect(secret).toMatch(/^nx_live_[A-Za-z0-9_-]{20,}$/)

  // "Done" stays disabled until the user confirms they stored the key
  const done = banner.getByRole('button', { name: 'Done' })
  await expect(done).toBeDisabled()
  await banner.getByLabel('I stored it somewhere safe').check()
  await done.click()
  await expect(banner).toBeHidden()
  await expect(page.getByRole('cell', { name: 'production-backend' })).toBeVisible()
  await expect(page.getByText('Never')).toBeVisible()
  expect(await page.content()).not.toContain(secret) // the secret is gone from the page once dismissed

  const r = await gateway.call(secret, 'first call')
  expect(r.status()).toBe(200)
  expect(r.headers()['x-nexora-request-id']).toMatch(/^req_/)
  expect((await r.json()).choices[0].message.content).toContain('first call')

  await page.reload()
  await expect(page.getByText('Never')).toBeHidden() // last used is now set

  await page.getByRole('link', { name: 'Logs' }).click()
  const row = page.getByRole('row').filter({ hasText: 'mock-1' })
  await expect(row).toHaveCount(1)
  await expect(row.getByText('Allowed')).toBeVisible()
  await row.focus()
  await page.keyboard.press('Enter') // rows open by keyboard too
  const drawer = page.getByRole('dialog', { name: 'Request details' })
  await expect(drawer).toContainText('req_')
  await expect(drawer).not.toContainText('first call') // prompt text is never stored
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
  await expect(row).toBeFocused() // focus returns to where the keyboard user was

  await page.getByRole('link', { name: 'Overview' }).click()
  await expect(page.getByText('Calls per day')).toBeVisible()
  await expect(page.getByRole('link', { name: /^Calls\s*1$/ })).toBeVisible()
})

test('the API key page rejects a blank name and shows the server message', async ({ page }) => {
  await page.goto('/app/keys')
  await page.getByLabel('Key name').fill('   ')
  await page.getByRole('button', { name: 'Create key' }).click()
  await expect(page.locator('p[role=alert]')).toContainText('blank')
})
