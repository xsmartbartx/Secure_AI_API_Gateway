# Build log (2026-10-13)

Repo restructured: `apps/api` (FastAPI), `apps/web` (Next.js 15.5.27), `docs/legacy` (Kong/K8s/DeepSeek leftovers, unused), `replica/` (planning).
Fixed from recon: adapter import name, missing `__init__.py`, merge-conflict file removed from the runtime path, plain-text errors -> JSON envelope, plaintext keys -> sha256 hashes.

| ID | screen | status | missing / notes |
| --- | --- | --- | --- |
| S01 | Home | done | no scroll animation; hero visual is the code sample |
| S02 | Security | done | copy states live vs coming |
| S03 | Pricing | done | Free/Starter match the live NEXORA plans; Team = contact |
| S06 | Legal | partial | draft placeholders, need lawyer review |
| S10 | Overview | done | single-series chart, no empty-chart state beyond "No calls yet" |
| S11 | API keys | done | reveal-once, revoke; rotate is API-only (no button yet); confirm uses `confirm()` not a modal |
| S12 | Playground | done | no streaming, no model picker |
| S13 | Usage | partial | by model only, no cost, no date range |
| S14 | Logs | done | decision filter + detail drawer; no pagination UI (limit 100), no CSV |
| S17 | Security events | partial | empty state only |
| S19 | Billing | partial | quota meter; checkout disabled until Stripe |
| S15,S16,S18,S20 | Providers/Policies/Team/Settings | stub | "On the roadmap" pages (honest, not faked) |
| S05,S07,S21,S22 | Status/Sign-in/Onboarding/Global states | todo | S07 depends on NEXORA SSO (backend step) |

Harder than expected: macOS sandbox blocked the preview launcher from running the venv binary under Desktop; API started via shell instead. Next 15.3.3 had a CVE, bumped to 15.5.27.
Verified: 9 API tests pass; `next build` clean (19 routes); UI loop key -> call -> overview in the browser, no console errors.
