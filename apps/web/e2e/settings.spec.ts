import { expect, test } from './fixtures'

test('delete organization: needs the typed name, then removes everything', async ({ page, gateway, org }) => {
  const { secret } = await gateway.createKey('doomed')
  await gateway.call(secret)

  await page.goto('/app/settings')
  await expect(page.getByText('kept for 7 days on the free plan')).toBeVisible()
  const del = page.getByRole('button', { name: 'Delete organization' })
  const input = page.getByLabel(/Type .* to confirm/)
  await expect(del).toBeDisabled()
  await input.fill(org.slice(0, -1))
  await expect(del).toBeDisabled()
  await input.fill(org)
  await expect(del).toBeEnabled()
  await del.click()
  await expect(page).toHaveURL(/localhost:3411\/$/)

  expect((await gateway.call(secret)).status()).toBe(401) // the key died with the organization
})

test('the first member of an organization is its owner and sees the delete form', async ({ page }) => {
  await page.goto('/app/settings')
  await expect(page.getByText('Your role')).toBeVisible()
  await expect(page.getByText('owner', { exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Delete organization' })).toBeVisible()
})
