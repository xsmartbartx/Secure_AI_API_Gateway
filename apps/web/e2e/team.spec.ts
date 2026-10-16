import { APIRequestContext } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { expect, test } from './fixtures'

const API = 'http://localhost:8411'
const as = (org: string, user: string, role = 'developer') => ({ 'x-dev-org': org, 'x-dev-user': user, 'x-dev-role': role })
const join = (request: APIRequestContext, org: string, user: string, role: string) => request.get(`${API}/api/me`, { headers: as(org, user, role) })

test('an owner changes a role and suspends and restores a member', async ({ page, request, org }) => {
  await page.goto('/app/team')                       // the browser user is the first member, so the owner
  await expect(page.getByRole('cell', { name: /demo@dev.local/ })).toBeVisible()
  for (const [u, r] of [['adm', 'admin'], ['dev', 'developer'], ['vw', 'viewer']]) await join(request, org, u, r)
  await page.reload()

  const own = page.getByRole('row').filter({ hasText: 'demo@dev.local' })
  await expect(own).toContainText('You')
  await expect(own.getByRole('combobox')).toHaveCount(0)             // nobody edits themselves
  await expect(own.getByRole('button')).toHaveCount(0)

  const dev = page.getByRole('row').filter({ hasText: 'dev@dev.local' })
  await dev.getByLabel('Role for dev@dev.local').selectOption('viewer')
  await expect.poll(async () => ((await (await request.get(`${API}/api/members`, { headers: as(org, 'demo') })).json()).items as { email: string; role: string }[]).find(m => m.email === 'dev@dev.local')?.role).toBe('viewer')

  page.once('dialog', d => { expect(d.message()).toContain('dev@dev.local'); d.accept() })
  await dev.getByRole('button', { name: 'Suspend' }).click()
  await expect(dev).toContainText('Suspended')
  expect((await request.get(`${API}/api/keys`, { headers: as(org, 'dev') })).status()).toBe(403)

  await dev.getByRole('button', { name: 'Restore' }).click()
  await expect(dev).toContainText('Active')
  expect((await request.get(`${API}/api/keys`, { headers: as(org, 'dev') })).status()).toBe(200)
})

test('an admin can only manage developers and viewers', async ({ page, request, org }) => {
  await join(request, org, 'founder', 'owner')       // first member = owner
  await join(request, org, 'dev', 'developer')
  await page.addInitScript(() => localStorage.setItem('devRole', 'admin'))
  await page.goto('/app/team')                       // the browser user joins as an admin
  await expect(page.getByRole('row').filter({ hasText: 'founder@dev.local' }).getByRole('combobox')).toHaveCount(0)
  await expect(page.getByRole('row').filter({ hasText: 'founder@dev.local' }).getByRole('button')).toHaveCount(0)
  const select = page.getByLabel('Role for dev@dev.local')
  await expect(select.locator('option')).toHaveText(['developer', 'viewer'])   // an admin is never offered owner or admin
  await select.selectOption('viewer')
  await expect(select).toHaveValue('viewer')
})

test('a suspended member is told why, and can still export their data and leave', async ({ page, request, org }) => {
  await join(request, org, 'founder', 'owner')
  await page.addInitScript(() => localStorage.setItem('devRole', 'developer'))
  await page.goto('/app/team')
  await expect(page.getByRole('cell', { name: /demo@dev.local/ })).toBeVisible()   // wait until the browser user has joined
  const me = ((await (await request.get(`${API}/api/members`, { headers: as(org, 'founder') })).json()).items as { id: string; email: string }[]).find(m => m.email === 'demo@dev.local')!
  await request.patch(`${API}/api/members/${me.id}`, { headers: as(org, 'founder'), data: { status: 'suspended' } })

  await page.reload()
  await expect(page.getByRole('heading', { name: 'Your access is suspended' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Team' })).toHaveCount(0)         // the dashboard itself is not shown
  expect((await new AxeBuilder({ page }).analyze()).violations.map(v => `${v.impact} ${v.id}`)).toEqual([])

  const [download] = await Promise.all([page.waitForEvent('download'), page.getByRole('button', { name: 'Download my data' }).click()])
  const mine = JSON.parse(await (await import('fs/promises')).readFile((await download.path())!, 'utf8'))
  expect(mine.member.email).toBe('demo@dev.local')

  page.once('dialog', d => d.accept())
  await page.getByRole('button', { name: 'Leave organization' }).click()
  await expect(page).toHaveURL(/localhost:3411\/$/)
  const left = ((await (await request.get(`${API}/api/members`, { headers: as(org, 'founder') })).json()).items as { email: string }[]).map(m => m.email)
  expect(left).toEqual(['founder@dev.local'])
})
