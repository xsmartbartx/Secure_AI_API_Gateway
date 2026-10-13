# Bugs

| ID | sev | title | status |
| --- | --- | --- | --- |
| B1 | S3 | Blank/whitespace key name accepted (creates unnamed key) | fixed, test `test_B1_blank_key_name_rejected` |
| B2 | S2 | API timestamps had no timezone (SQLite); browsers parse as local time so times can be off by the UTC offset | fixed (`UTCDateTime` type), test `test_B2_timestamps_are_utc_aware`; verified in UI (logs time = local clock) |
| B5 | S4 | Invalid JSON body gave message "0: JSON decode error" | fixed, test `test_B5_invalid_json_message` |

## B2 detail
Steps: create key, call /v1/chat, GET /api/logs. Expected `ts` like `2026-10-13T09:37:20Z`. Actual `2026-10-13T09:37:20` (no zone) so dashboard would show 09:37 in a UTC+2 browser instead of 11:37.

## To check (not reproduced / not bugs yet)
- T1 `/docs` and `/openapi.json` are public on the API. Decide whether to keep for developers or disable in prod.
- T2 Quota check is count-per-call (race: concurrent calls can overshoot by a few). Acceptable for MVP; use a Redis counter.
- T3 Key rotate has no UI and no explicit test that the old key keeps working until revoked.
- T4 Revoke uses browser `confirm()`; replace with the spec'd dialog (types key name).
- T5 Mobile nav drawer has no backdrop; tapping outside does not close it.
- T6 Redis limiter and Stripe test mode never run against the real services.

Open S1: none. Open S2: none.
