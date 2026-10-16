import { expect, test } from './fixtures'

const GOOD = 'sk-ant-e2e-0001-abcdEFGH1234'
const BAD = 'sk-ant-bad-0000-abcdEFGH5678'

test('add, test, switch default and remove a provider key', async ({ page, dev, request }) => {
  await page.goto('/app/providers')
  await expect(page.getByText('No provider keys yet')).toBeVisible()

  // a key the provider rejects is refused and nothing is stored
  await page.getByLabel('Name').fill('broken')
  await page.getByLabel('API key').fill(BAD)
  await page.getByRole('button', { name: 'Verify and save' }).click()
  await expect(page.locator('p[role=alert]')).toContainText('rejected that API key')
  await expect(page.getByLabel('API key')).toHaveValue('') // the key never stays in the form
  await expect(page.getByText('No provider keys yet')).toBeVisible()

  await page.getByLabel('Name').fill('production')
  await page.getByLabel('API key').fill(GOOD)
  await page.getByRole('button', { name: 'Verify and save' }).click()
  const row = page.getByRole('listitem').filter({ hasText: 'production' })
  await expect(row).toContainText('Anthropic')
  await expect(row).toContainText('…1234')     // only the last four characters
  await expect(row).toContainText('Default')
  await expect(row).toContainText('Working')
  expect(await page.content()).not.toContain(GOOD)

  // the API never returns the key either
  const list = await request.get('http://localhost:8411/api/providers', { headers: dev })
  expect(await list.text()).not.toContain('abcdEFGH')

  await page.getByLabel('Provider').selectOption('openai')
  await page.getByLabel('Name').fill('backup')
  await page.getByLabel('API key').fill('sk-proj-e2e-0002-abcdEFGH9999')
  await page.getByRole('button', { name: 'Verify and save' }).click()
  const backup = page.getByRole('listitem').filter({ hasText: 'backup' })
  await expect(backup).toContainText('OpenAI')
  await expect(backup).not.toContainText('Default')

  await backup.getByRole('button', { name: 'Test' }).click()
  await expect(backup).toContainText('Working')
  await backup.getByRole('button', { name: 'Make default' }).click()
  await expect(backup).toContainText('Default')
  await expect(row).not.toContainText('Default')

  page.once('dialog', d => d.accept())
  await row.getByRole('button', { name: 'Remove' }).click()
  await expect(row).toHaveCount(0)
  await expect(backup).toContainText('Default')
})

test('developers can see provider keys but not change them', async ({ page, request, org }) => {
  // someone else created the organization first, so this browser's user joins as a developer
  await request.get('http://localhost:8411/api/me', { headers: { 'x-dev-org': org, 'x-dev-user': 'founder' } })
  await page.addInitScript(() => localStorage.setItem('devRole', 'developer'))
  await page.goto('/app/providers')
  await expect(page.getByText('Only admins and owners can add or remove keys.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Verify and save' })).toHaveCount(0)
})
