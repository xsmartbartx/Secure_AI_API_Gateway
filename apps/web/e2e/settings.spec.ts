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

test('export: an admin downloads a JSON file with their data and no secrets', async ({ page, gateway }) => {
  const { secret } = await gateway.createKey('exported-key')
  await gateway.call(secret, 'a prompt that must never be stored')
  await page.goto('/app/settings')
  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download organization data' }).click()])
  expect(download.suggestedFilename()).toMatch(/^nexora-gateway-export-.+\.json$/)
  const text = await (await import('fs/promises')).readFile((await download.path())!, 'utf8')
  const d = JSON.parse(text)
  expect(d.api_keys.map((k: { name: string }) => k.name)).toEqual(['exported-key'])
  expect(d.request_logs).toHaveLength(1)
  for (const secretish of [secret, 'key_hash', 'credential_enc', 'a prompt that must never be stored']) expect(text).not.toContain(secretish)

  const [mine] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download my own record' }).click()])
  expect(JSON.parse(await (await import('fs/promises')).readFile((await mine.path())!, 'utf8')).member.role).toBe('owner')
})

test('a developer can export only their own record', async ({ page, request, org }) => {
  await request.get('http://localhost:8411/api/me', { headers: { 'x-dev-org': org, 'x-dev-user': 'founder' } })
  await page.addInitScript(() => localStorage.setItem('devRole', 'developer'))
  await page.goto('/app/settings')
  await expect(page.getByRole('button', { name: 'Download my own record' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Download organization data' })).toHaveCount(0)
})
