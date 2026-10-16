import { expect, test } from './fixtures'

const PAGES = ['/', '/pricing', '/security', '/data-handling', '/app', '/app/keys', '/app/logs', '/app/usage', '/app/playground', '/app/billing', '/app/settings']

test.describe('390px phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  for (const path of PAGES) {
    test(`no horizontal scroll on ${path}`, async ({ page }) => {
      await page.goto(path)
      await expect(page.locator('h1').first()).toBeVisible()
      const { sw, cw } = await page.evaluate(() => ({ sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth }))
      expect(sw).toBeLessThanOrEqual(cw)
    })
  }

  test('the dashboard menu opens and closes and navigates', async ({ page }) => {
    await page.goto('/app')
    const nav = page.getByRole('navigation', { name: 'Dashboard' })
    await expect(nav).not.toBeInViewport()
    await page.getByRole('button', { name: 'Open menu' }).click()
    await expect(nav).toBeInViewport()
    await nav.getByRole('link', { name: 'API keys' }).click()
    await expect(page).toHaveURL(/\/app\/keys$/)
    await expect(nav).not.toBeInViewport() // closes after navigating
  })
})
