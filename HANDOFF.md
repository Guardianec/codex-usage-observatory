# Codex Usage Observatory — current handoff

Both phases are complete: verified telemetry foundation and full local product UI.
This replaces the original instruction to build the frontend. No telemetry research
needs repeating to maintain the product.

## Launch / test

```powershell
npm ci
npm run build
npm start
python -m unittest discover -v
npm test
npm run test:e2e
```

Open `http://127.0.0.1:8765`. Subsequent launches: `npm start`. Python 3.11+;
Node 20.19+ or 22.12+ for builds. Built runtime uses only Python. Data/settings
default to `.local/observatory.sqlite` and `.local/settings.json`. CODEX_HOME or
`~/.codex` supplies read-only sources. CLI flags remain documented in README.

## Architecture

| Component | Files / boundary |
|---|---|
| Authoritative token domain | `observatory/domain.py`: Usage validation/arithmetic and Decimal estimator; unchanged |
| Adapter / ingestion | `adapter.py`, `ingest.py`: rollout-v1 allowlist, bounded append reader, atomic checkpoints, global response deduplication; unchanged |
| SQLite / original queries | `db.py`, `service.py`: schema v1, constraints/indexes/WAL and original aggregate boundary; unchanged |
| Product read models | `analytics.py`: SQL grouping, task/request pages, medians/comparisons, bounded timelines, explicit thread/root attribution |
| Preferences | `settings.py`: strict thresholds/rates validation and atomic local JSON replacement |
| HTTP | `api.py`: original API/SSE plus product queries, exports, same-origin settings, static SPA/deep-link serving |
| Frontend pages | `frontend/src/main.tsx`: Overview, Live, Tasks/detail, Sessions/detail, Projects/detail, Models, Agents, Insights, Settings |
| UI primitives / state | `components.tsx`, `core.tsx`, `format.mjs`: metrics, charts, tables, API/SSE, URL state, preferences, display helpers |
| Design | `styles.css`: graphite/mint dark, warm light, Plex Sans/Mono, compact responsive shell, contained table scrolling |
| Build / QA | React/TypeScript/Vite, bundled fonts and Lucide, lockfile; Python, Node unit and Playwright behavior/visual tests |

## Invariants to preserve

1. Count only dedicated per-response usage once per global response ID.
2. Cached input is inside input; reasoning is inside output. Total = input + output.
3. Request count means recorded responses; failed attempts without usage are unknown.
4. Thread ID and root session ID are different identities. Child threads stay separate.
5. Task key = (thread,turn), with explicit lifecycle/root/parent IDs. Automatic turns
   exist. Never invent human-operation grouping or prompt-derived names.
6. Model/effort are per-response context snapshots; unknown stays unknown.
7. Agent views use explicit parent_thread_id and each thread's own responses.
   General spawned agents/forks remain unverified. Never add cumulative parent totals.
8. Rows/checkpoints commit together. Append assumptions, 8 MiB line bound, partial
   line deferral, replay detection and conflicting-response diagnostics remain intact.
9. Frontend receives normalized metrics; it computes display ratios, clocks,
   comparison multiples and geometry, never independent accounting totals.
10. Token counts cannot establish quota, invoices or model quality.

Evidence remains in `docs/codex-telemetry.md` and `docs/verification.md`. Local numeric verification passed. Detailed machine-specific figures are private
and excluded from publication; regenerate them into .local/reports when needed.

## Product semantics and API

Date filters select response timestamps; turn medians use contributions in range.
Unknown turns are counted separately. Model medians use each model's contribution
inside mixed-model turns; duration stays whole-turn wall time including tools/waiting.
Rates use recorded buckets/known turn durations, not claimed inference speed.
Running means last known running. Daily bins are UTC; calendar ranges use browser
local days. Task/session details show whole entities; project details retain scope.

No DB migration was needed. Original endpoints are compatible. Additions:

- `/api/analytics`: summary/distributions/daily/current/recent/expensive/cost.
- `/api/history`: filtered/sorted task pages, 25 default, 100 max.
- `/api/requests`: normalized response pages, 50 default, 100 max.
- `/api/timeline`: approximately 120 chronological buckets, explicit idle gaps.
- `/api/session-history`: paginated thread summaries, own usage only.
- `/api/task-detail`: full turn, pricing coverage, median baselines.
- `/api/export?kind=tasks|daily|statistics`: CSV or normalized JSON.
- `/api/settings` GET/POST: validated local preferences plus runtime info on GET.

Full contracts: `docs/product.md`. Existing tables remain projects, sessions, tasks,
responses, checkpoints, diagnostics. Python serves frontend/dist with CSP and known
SPA route fallback. Host/Origin and static path traversal are validated. No runtime
CDN or external calls. The Vite development proxy targets Python on port 8765.

Browser localStorage holds theme/landing/timezone; server settings holds thresholds
and exact-model USD rates. The original estimator applies per UTC response date;
unpriced/partially covered usage remains explicit. No subscription conversion exists.

## Verification and QA

Final: **40 Python tests**, **4 frontend unit tests**, **8 Playwright scenarios** pass.
The original 33 backend tests remain intact. Production TypeScript/Vite build passes.
Required screens were captured at 1440×900, 1280×800, 1024×768, plus light theme
and 390 px. Refinement fixed timezone mismatch, idle gaps, model-view spacing and
pinned-total overlap. Charts support keyboard inspection/data tables.

`node scripts/visual-qa.mjs` requires the real app on 8765 and writes ignored local
screenshots/report. E2E uses an isolated fixture source and new DB on 8877. Chromium
installation: `npx playwright install chromium`. Restricted Windows execution needs
loopback/browser permission. See `docs/product-qa.md`.

## Boundaries / future maintenance

Local single-user application; no remote hosting, installer, authentication,
encryption, process supervisor or automatic Codex control. Source selection is a
launch flag. Safe reimport targets a new DB rather than destroying current history.
Daily UI caps at 730 days, session detail previews 100 turns with a full-history
link, Agents loads 100 threads with missing-parent labels, exports cap at 50,000
rows. Very large task archives may eventually need SQL-native percentile/pagination
optimization; grouped rows currently stay server-side. Do not preemptively rewrite
the verified core. Future work should follow actual user feedback/compatibility evidence.
