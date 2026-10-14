import { expect, test } from './fixtures'

test('usage per key, model and day, with totals and a CSV download', async ({ page, gateway }) => {
  const a = await gateway.createKey('alpha')
  const b = await gateway.createKey('=HYPERLINK("http://evil")')
  for (let i = 0; i < 3; i++) await gateway.call(a.secret, `a${i}`)
  await gateway.call(b.secret, 'b0')

  await page.goto('/app/usage')
  const rows = page.getByRole('row')
  await expect(rows.filter({ hasText: 'alpha' })).toContainText('3')
  await expect(page.getByRole('row', { name: /^Total/ })).toContainText('4')

  await page.getByRole('button', { name: 'By model' }).click()
  await expect(page.getByRole('row').filter({ hasText: 'mock-1' })).toContainText('4')
  await page.getByRole('button', { name: 'By day' }).click()
  await expect(page.getByRole('img', { name: /Calls per day/ })).toBeVisible()
  await page.getByRole('button', { name: 'By key' }).click()

  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download CSV' }).click()])
  expect(download.suggestedFilename()).toMatch(/^usage-key-\d{4}-\d{2}-\d{2}-\d{4}-\d{2}-\d{2}\.csv$/)
  const csv = (await (await import('fs/promises')).readFile((await download.path())!, 'utf8')).trim().split(/\r?\n/)
  expect(csv[0]).toBe('label,calls,blocked,errors,tokens_in,tokens_out')
  expect(csv.some(l => l.startsWith('alpha,3,'))).toBe(true)
  // a key named like a formula cannot run in a spreadsheet: the cell is prefixed with ' (the field is CSV-quoted because it contains quotes)
  expect(csv.some(l => l.startsWith(`"'=HYPERLINK(`))).toBe(true)
  expect(csv.some(l => /^"?=/.test(l))).toBe(false)
})

test('an invalid date range is explained and a preset recovers', async ({ page }) => {
  await page.goto('/app/usage')
  await page.getByLabel('To', { exact: true }).fill('2026-01-01')
  await page.getByLabel('From', { exact: true }).fill('2026-02-01')
  await expect(page.locator('p[role=alert]')).toContainText('"From" must not be after "To"')
  await page.getByRole('button', { name: 'Last 7d' }).click()
  await expect(page.locator('p[role=alert]')).toHaveCount(0)
  await expect(page.getByText('No calls in this range')).toBeVisible()
})
