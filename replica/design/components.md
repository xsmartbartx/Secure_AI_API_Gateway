# Components: NEXORA Gateway

Principles: Azure-portal density and IA inside the dashboard; Apple-style restraint on marketing (one idea per section, `display` type, 96-128px section gaps, quiet motion). Base: Radix primitives + Tailwind. Icons: Lucide. Font: Inter / JetBrains Mono. All colours via role tokens. Motion respects `prefers-reduced-motion`.

Global a11y: every control keyboard reachable, 2px `accent` focus ring with 2px offset, touch targets >= 40px on mobile, status never conveyed by colour alone (icon + text), dark mode parity.

## App shell (S10-S22)
  layout   header 48px (logo, org switcher, search/command palette Cmd+K, theme, user), left nav 240px (collapses to 56px, drawer < 1024px), breadcrumb row, content max 1280
  nav      Overview, Playground, API keys, Logs, Usage, Security, Providers, Policies, Team, Billing, Settings; nav-bg dark in both themes
  states   loading skeleton, org-less (-> onboarding), maintenance banner, quota banner
  a11y     landmarks (header/nav/main), skip link, `aria-current="page"`

## Button
  variants primary, secondary, ghost, danger, link
  sizes    sm 32, md 40, lg 48
  states   default, hover, active, focus-visible, disabled, loading (spinner + label retained, `aria-busy`)
  tokens   primary bg accent / on-accent; radius md; text sm/600
  used on  all

## Input / Select / Textarea / Switch / Checkbox
  states   default, hover, focus, filled, error (danger border + message + icon, `aria-describedby`), disabled, read-only
  tokens   border-input, radius md, height 40
  a11y     visible label always, helper text linked

## KPI tile
  content  label, value (xl), delta chip, sparkline; click -> filtered page
  states   loading, empty ("No calls yet" + CTA), error (retry)
  used on  S10, S13

## Chart (time series, stacked bar, donut)
  rules    one hue family + neutrals; tooltip, legend toggles, table view toggle for a11y; palette from tokens (accent, success, warning, danger, text-muted)
  states   loading, empty, error
  used on  S10, S13

## Data table
  features sticky header, sort, column filters, density toggle, cursor pagination, CSV export, row click -> drawer, bulk select (keys)
  states   loading skeleton rows, empty (illustration-free, icon + text + CTA), no-match (clear filters), error
  a11y     real `<table>`, sortable headers are buttons with `aria-sort`
  used on  S11, S13, S14, S17, S18

## Detail drawer
  right panel 480px; tabs Request / Decision / Raw metadata; copy-id; Esc closes; focus trapped, returns focus to row
  used on  S14, S17

## Modal / Confirm dialog
  sizes sm 400 / md 560; destructive confirm requires typing resource name for key revoke and org delete
  a11y  Radix Dialog, `aria-labelledby`

## Reveal-once secret
  shows key once with Copy, mono, warning banner "You won't see this again", checkbox "I stored it" enables Done
  used on S11, S15

## Code block
  language tabs (curl, Python, Node), copy button, line wrap toggle, mono 13px, theme-aware syntax tokens
  used on S01, S04, S12, S21

## Status pill
  allow (success + check), flag (warning + alert), block (danger + shield-x), error (text-muted + x); icon + label always

## Risk meter
  0-100 bar with bands Low/Medium/High/Critical; number + label

## Toast
  bottom-right, 5s, `role="status"`; error toasts persist until dismissed

## Banner
  info, warning (quota 80%), danger (quota exceeded / provider failing), maintenance; dismissible except danger

## Empty state
  icon, one-line title, one-line help, primary action; written per screen (no stock copy)

## Plan card / comparison table
  highlight current plan, feature rows with check/dash, monthly/annual toggle; Free $0 / 100 calls, Starter $19 / 1,500 calls (live today), Team and Enterprise "Contact"
  used on S03, S19

## Stepper (onboarding)
  3 steps: Create key -> Make a call -> See it logged; completes when first log row appears (polls /api/logs)
  used on S21

## Command palette
  Cmd+K: jump to page, search keys/log ids; Radix + cmdk

## Marketing blocks (S01-S03)
  Hero (display type, one CTA primary + one link), flow diagram "Key. Call. Govern." (SVG, original), feature rows alternating copy/visual, code sample, trust strip (honest "What's real today" list, no badge wall), CTA band, footer (NEXORA parent link, Docs, Status, Legal)
  motion  fade/translate 8px on scroll, 200ms ease; disabled with reduced motion

## Global states (S22)
  404, 403, 429 (quota), 500, maintenance: full-page, one action each
