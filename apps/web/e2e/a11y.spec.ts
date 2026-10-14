import AxeBuilder from '@axe-core/playwright'
import { expect, test } from './fixtures'

const PAGES = ['/', '/pricing', '/security', '/data-handling', '/terms', '/privacy',
  '/app', '/app/playground', '/app/keys', '/app/logs', '/app/usage', '/app/security', '/app/providers',
  '/app/policies', '/app/team', '/app/billing', '/app/settings']

for (const theme of ['light', 'dark'] as const) {
  for (const path of PAGES) {
    test(`axe: ${path} (${theme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme })
      await page.addInitScript(t => { try { localStorage.setItem('theme', t) } catch {} }, theme)
      await page.goto(path)
      await expect(page.locator('h1').first()).toBeVisible()
      await page.waitForLoadState('networkidle')
      const { violations } = await new AxeBuilder({ page }).withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa', 'best-practice']).analyze()
      expect(violations.map(v => `${v.impact} ${v.id}: ${v.help} (${v.nodes.length}) ${v.nodes[0]?.target.join(' ')}`)).toEqual([])
    })
  }
}

test('axe: dashboard with data (keys table, logs table, drawer, key reveal banner)', async ({ page, gateway }) => {
  const { secret } = await gateway.createKey('axe-key')
  await gateway.call(secret)
  await page.goto('/app/keys')
  await page.getByLabel('Key name').fill('another')
  await page.getByRole('button', { name: 'Create key' }).click()
  await expect(page.getByRole('alert').filter({ hasText: "You won't see it again" })).toBeVisible()
  let r = await new AxeBuilder({ page }).analyze()
  expect(r.violations.map(v => `${v.impact} ${v.id} ${v.nodes[0]?.target.join(' ')}`)).toEqual([])
  await page.goto('/app/logs')
  await page.getByRole('row').filter({ hasText: 'mock-1' }).click()
  await expect(page.getByRole('dialog', { name: 'Request details' })).toBeVisible()
  r = await new AxeBuilder({ page }).analyze()
  expect(r.violations.map(v => `${v.impact} ${v.id} ${v.nodes[0]?.target.join(' ')}`)).toEqual([])
})

// Guards against a vacuous suite: axe must flag a violation we plant, so a clean result means something.
test('axe canary: a planted violation is detected', async ({ page }) => {
  await page.goto('/pricing')
  await page.evaluate(() => {
    document.body.insertAdjacentHTML('beforeend', '<img src="/icon.svg"><button></button><input type="text">')
  })
  const { violations } = await new AxeBuilder({ page }).analyze()
  const ids = violations.map(v => v.id)
  expect(ids).toEqual(expect.arrayContaining(['image-alt', 'button-name', 'label']))
})
