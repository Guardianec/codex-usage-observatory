# Product QA — 2026-10-16

The original 33-test baseline passed before implementation. Domain, adapter,
ingestion, schema and original aggregate service were preserved.

| Final check | Result |
|---|---|
| `python -m unittest discover -v` | 40 passed, including new analytics/product API/settings security checks |
| `npm test` | 4 passed: formatting, duration, calendar ranges, warning severity |
| `npm run build` | TypeScript and Vite production build passed |
| `npm run test:e2e` | 8 Playwright scenarios passed against isolated local fixture telemetry |
| `node scripts/visual-qa.mjs` | No page errors or page-level horizontal overflow in required captures |

Browser coverage: real API totals, live/chart modes, search/filter/sort/pagination,
task deep-link refresh, session/project detail, dynamic model comparison and effort
filtering, custom empty ranges, absent agents, unavailable detail, theme/settings
persistence, CSV download, API failure/retry, narrow navigation, keyboard focus and
live-to-idle lifecycle updates. Fixtures never enter production. HTTP checks also
verify endpoints, export fields, foreign-Origin rejection and invalid settings.

The live scenario appends a new usage record and verifies the displayed total
changes from 10,200 to 10,320 before completing the turn. Chart arrow-key tooltips
are exercised. The 250-session / 10,001-response benchmark produced its complete
grouped product payload in 0.0922 seconds and 16,070 bytes; unchanged warm ingestion
parsed zero archive bytes. This is a sanity check, not a concurrency stress test.

## Visual inspection and refinement

Captured Overview, Live, Tasks, Turn Detail, Models and Settings at **1440×900**,
**1280×800**, **1024×768**: 18 required desktop captures. Also captured Overview and
Settings in light mode and Overview at **390×844**. Captures/report remain ignored
in `.local/screenshots` and `.local/visual-report.json` because real project metadata
is visible. Font loading is awaited and transitions disabled for stable captures.

Deliberate refinements after inspecting rendered output:

- Unified timezone-aware turn labels and surrounding timestamps.
- Preserved idle buckets instead of joining rates across silence.
- Tightened model composition spacing and retained detailed comparison statistics.
- Corrected pinned-total overlap; preserved model identity in wide tables.
- Refined laptop layouts with contained horizontal table scrolling.
- Added keyboard chart inspection and accessible data tables.
- Ordered warning reasons by the threshold driving severity.
- Kept missing usage, pricing gaps, errors and stale running state explicit.

Both themes and all required screens were inspected in Chromium. Safari/Firefox
and screen-reader audits were not performed. Mobile is a graceful fallback.
Restricted Windows execution needed approved loopback/browser permissions. No
production upload, external telemetry or deployment was created.
