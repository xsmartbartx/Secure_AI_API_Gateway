import { defineConfig } from '@playwright/test'

const WEB = 'http://localhost:3411'
const API = 'http://localhost:8411'

// Ports 3411/8411 are unlikely to collide with other projects' dev servers. If one is busy Playwright fails loudly.
// Runs against a production build of the web app and a fresh API with SQLite and the mock upstream.
// Uses the installed Google Chrome (channel: 'chrome'); on a machine without it run `npx playwright install chromium`
// and change the channel.
export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 7_000 },
  fullyParallel: true,
  workers: process.env.CI ? 2 : 4,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list'], ['html', { open: 'never' }]],
  use: { baseURL: WEB, channel: 'chrome', trace: 'retain-on-failure', screenshot: 'only-on-failure' },
  webServer: [
    {
      command: 'rm -f e2e.db && .venv/bin/uvicorn app.main:app --port 8411',
      cwd: '../api',
      url: `${API}/v1/health`,
      reuseExistingServer: !!process.env.PW_REUSE, // never silently test whatever else is listening on the port
      timeout: 60_000,
      env: {
        DATABASE_URL: 'sqlite+aiosqlite:///./e2e.db', ENV: 'dev', DEV_AUTH: 'true', ALLOW_MOCK_UPSTREAM: 'true',
        ANTHROPIC_API_KEY: '', OPENAI_API_KEY: '', STRIPE_SECRET_KEY: '', MOCK_STREAM_DELAY_MS: '150',
        RETENTION_JOB_ENABLED: 'false', MOCK_PROVIDER_CHECK: 'true', CORS_ORIGINS: WEB,
      },
    },
    {
      command: 'npm run build && npm run start -- -p 3411',
      url: WEB,
      reuseExistingServer: !!process.env.PW_REUSE, // never silently test whatever else is listening on the port
      timeout: 240_000,
      env: { NEXT_DIST_DIR: '.next-e2e', NEXT_PUBLIC_API_BASE: API, NEXT_PUBLIC_DEV_AUTH: '1' },
    },
  ],
})
