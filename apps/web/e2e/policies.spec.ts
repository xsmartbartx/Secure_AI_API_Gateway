import AxeBuilder from '@axe-core/playwright'
import { expect, test } from './fixtures'

test('an admin turns on enforcement and blocked calls show up in logs, security events and the overview', async ({ page, gateway }) => {
  const { secret } = await gateway.createKey('policy-key')
  await page.goto('/app/policies')
  await expect(page.getByRole('radio', { name: /Off/ })).toBeChecked()

  await page.getByRole('radio', { name: /Enforce/ }).check()
  await page.getByLabel('Models on the list').fill('mock-*\nGPT-4o')
  page.once('dialog', d => { expect(d.message()).toContain('rejected immediately'); d.accept() })
  await page.getByRole('button', { name: 'Save policy' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Saved (version 1)' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save policy' })).toBeDisabled() // nothing left to save

  // dry run against the saved policy
  await page.getByLabel('Model', { exact: true }).fill('gpt-4o')
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'matches' })).toContainText('gpt-4o')
  await page.getByLabel('Model', { exact: true }).fill('claude-opus-9')
  await page.getByRole('button', { name: 'Check' }).click()
  await expect(page.getByRole('status').filter({ hasText: 'Blocked' })).toBeVisible()

  expect((await gateway.call(secret, 'ok', { model: 'mock-1' })).status()).toBe(200)
  const blocked = await gateway.call(secret, 'nope', { model: 'claude-opus-9' })
  expect(blocked.status()).toBe(403)
  expect((await blocked.json()).error.code).toBe('model_not_allowed')

  await page.getByRole('link', { name: 'Logs' }).click()
  await page.getByLabel('Filter by decision').selectOption('block')
  const row = page.getByRole('row').filter({ hasText: 'claude-opus-9' })
  await expect(row).toContainText('Blocked')
  await expect(row).toContainText('403')

  await page.getByRole('link', { name: 'Security' }).click()
  await expect(page.getByRole('row').filter({ hasText: 'Call blocked: model not allowed' })).toContainText('model: claude-opus-9')

  await page.getByRole('link', { name: 'Overview' }).click()
  await expect(page.getByRole('link', { name: /^Blocked\s*1$/ })).toBeVisible()
  expect((await new AxeBuilder({ page }).analyze()).violations.map(v => `${v.impact} ${v.id}`)).toEqual([])
})

test('monitor mode lets calls through and flags the ones that would be blocked', async ({ page, gateway }) => {
  const { secret } = await gateway.createKey('monitor-key')
  await page.goto('/app/policies')
  await page.getByRole('radio', { name: /Monitor/ }).check()
  await page.getByLabel('Models on the list').fill('gpt-4o')
  await page.getByRole('button', { name: 'Save policy' }).click()      // no confirmation: monitoring blocks nothing
  await expect(page.getByRole('status').filter({ hasText: 'Saved' })).toBeVisible()

  expect((await gateway.call(secret, 'x', { model: 'mock-1' })).status()).toBe(200)
  await page.goto('/app/logs')
  await page.getByLabel('Filter by decision').selectOption('flag')
  await expect(page.getByRole('row').filter({ hasText: 'mock-1' })).toContainText('Flagged')
})

test('turning the policy on with an empty list is refused with an explanation', async ({ page }) => {
  await page.goto('/app/policies')
  await page.getByRole('radio', { name: /Monitor/ }).check()
  await page.getByRole('button', { name: 'Save policy' }).click()
  await expect(page.locator('p[role=alert]')).toContainText('at least one model')
})

test('developers can read the policy but not change it', async ({ page, request, org }) => {
  await request.get('http://localhost:8411/api/me', { headers: { 'x-dev-org': org, 'x-dev-user': 'founder' } })
  await page.addInitScript(() => localStorage.setItem('devRole', 'developer'))
  await page.goto('/app/policies')
  await expect(page.getByText('Only admins and owners can change policies.')).toBeVisible()
  await expect(page.getByRole('button', { name: 'Save policy' })).toHaveCount(0)
  await expect(page.getByLabel('Models on the list')).toHaveAttribute('readonly', '')
  await expect(page.getByRole('radio', { name: /Enforce/ })).toBeDisabled()
})
