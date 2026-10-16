# Codex Usage Observatory

A local developer tool for recorded Codex usage: live turns, request traces,
searchable history, sessions, projects, models, explicit agent relationships,
deterministic insights and optional API-equivalent estimates.

## Install and launch

Requires Python 3.11+ with SQLite, and Node.js 20.19+ or 22.12+ for building.
Verified on Windows with Python 3.13.1 and Node 22.12.0. From this directory:

```powershell
npm ci
npm run build
npm start
```

Open [Observatory](http://127.0.0.1:8765). Subsequent launches need only `npm start`.
The Python service serves the built UI and API together, imports history and follows
new files/appends every two seconds. Stop with Ctrl+C. The built product needs only
Python at runtime. Fonts, icons and scripts are bundled; no external runtime requests.

Source defaults to CODEX_HOME or `%USERPROFILE%/.codex`. Data is persisted in
`.local/observatory.sqlite`, thresholds/rates in `.local/settings.json`.

```powershell
python -m observatory serve --codex-home "C:\path\to\.codex" --port 8765
python -m observatory status
python -m observatory import
```

Other flags: `--db PATH`, `--interval 2` (minimum one second), `--debug`. Keep the
database outside the Codex source directory. Dependencies are project-local.

## Application

- **Overview / Live:** current or latest turn, nested token breakdown, cumulative,
  rate and response-event traces, date-range summaries, daily usage, recent turns,
  distributions, response history and calm threshold warnings.
- **Tasks:** server-filtered search, project/model/observed-effort/status filters,
  sorting, pagination, pinned totals and CSV export. Detail includes normalized
  responses, context/cache insight and median comparisons.
- **Sessions / Projects:** chronological turn exploration, usage timelines, models,
  medians, largest turns and drilldowns.
- **Models:** dynamically discovered models, contribution/duration comparisons,
  composition, detailed statistics, observational rates and optional costs.
- **Agents:** explicit parent/child thread links and each thread's own usage;
  unsupported attribution and missing parents are labeled.
- **Insights:** local mathematical observations, without a language model.
- **Settings:** dark/light/system themes, landing page, display timezone, thresholds,
  optional USD rates, privacy, connection information and advanced diagnostics.

Today/7/30/custom ranges use the browser's local calendar; custom includes the whole
selected end date. Daily bars are UTC, so local intervals can include partial UTC
dates. Filters live in the URL and detail links survive refresh. Task/session detail
shows the whole entity; project detail retains date scope. Focus a chart and use
arrow keys to inspect values, or open its data table.

Theme, landing page and timezone are browser preferences. Thresholds/rates are
saved explicitly to local settings. Warnings never stop Codex.

## Token and cost semantics

- Input includes cached input. Uncached = input − cached.
- Output includes reasoning. Total = input + output.
- Request count means unique recorded response IDs, not network attempts.
- A task is an observed Codex turn; human operations can span multiple turns.
- A session row is one thread's own usage. Children are linked explicitly;
  cumulative parent counters are never added again.
- Last known running is a telemetry state, not proof of process liveness.
- Unknown/missing usage is labeled; zero recorded tokens does not prove zero usage.

Supported dedicated usage records were observed in CLI versions
0.162.0-alpha.17.2 and 0.163.0-alpha.10.2. Legacy summary-only accounting is unsupported.
See [telemetry investigation](docs/codex-telemetry.md) and
[real-data verification](docs/verification.md).

Pricing is optional. Settings accepts exact model IDs, effective dates and USD
rates per million tokens. No prices are supplied/downloaded. Format example:

```json
[{"model":"your-model-id","effective_date":"2026-01-01","uncached_input_per_million":0,"cached_input_per_million":0,"output_per_million":0}]
```

Replace these example fields with your authoritative rates. The original Decimal
estimator applies per model and UTC response date. Missing rates remain unavailable;
partial estimates disclose coverage (`*` in task tables). These are hypothetical
API-equivalent costs, not subscription charges, invoices or quota percentages.

## Privacy

All analysis runs locally. No analytics, uploads, prompt storage, credentials access
or cloud database. Codex files are read-only. The database retains IDs, timestamps,
model/effort, project basename/hash, counters and private source checkpoint paths.
Settings deliberately shows source/database locations on localhost for troubleshooting.

The service binds to IPv4 loopback, validates Host/Origin, permits only same-origin
settings writes and serves a restrictive content security policy. It is a single-user
local application. Files rely on OS access controls and are not encrypted. Never
share the DB or commit `.local`. Exports contain normalized metadata/metrics, not
prompts; CSV strings are protected against formula injection. Real QA screenshots
remain ignored because they contain project metadata.

## Development and tests

For hot reload, keep Python running and run `npm run dev` separately. Vite proxies
API calls to port 8765. Production needs only the single Python origin.

```powershell
python -m unittest discover -v
npm test
npm run test:e2e
node scripts/visual-qa.mjs
```

If needed, install the test browser with `npx playwright install chromium`.
Playwright E2E starts an isolated fixture application on 8877; no test data enters
production. Visual QA uses the real service on 8765. Restricted Windows sandboxes
may need permission for loopback HTTP and browser processes.

Verified: **40 Python tests**, **4 frontend unit tests**, **8 Playwright scenarios**,
TypeScript/Vite build. Visual QA covered six required screens at 1440×900, 1280×800
and 1024×768, light mode, and a 390 px fallback. See [QA evidence](docs/product-qa.md).

Foundation tools remain available: `python -m scripts.verify_local` independently
compares raw numeric fields with SQLite and writes its private report under
`.local/reports/verification.md`. `python -m scripts.benchmark` uses synthetic data
and updates [performance results](docs/performance.md). The shared
[verification note](docs/verification.md) contains no personal usage figures.

## Troubleshooting and limits

- Missing sessions: check Settings → Local connection, launch with the correct
  `--codex-home`, and clear date/search filters. Unsupported formats remain unknown.
- Disconnected: keep `npm start` running. The browser reconnects automatically;
  Refresh retries API queries while previously loaded data remains visible.
- Unsupported/malformed/conflicting telemetry: inspect Settings → Advanced
  diagnostics. Raw prompts and stack traces are not shown.
- Missing UI after checkout: run `npm ci` and `npm run build`.
- Invalid settings: use positive thresholds, finite nonnegative USD rates, valid
  YYYY-MM-DD dates and unique model/date pairs.
- Source changes require a restart with the CLI flag. Safe reimport uses a separate
  DB: `python -m observatory import --db .local/review.sqlite`.
- General collaboration agents/forks, failed attempts without usage and provider
  billing completeness remain unverified. Durations include tools/waiting.
- Daily charts show at most 730 days with notice; exports include the full recorded
  range. Session detail previews 100 turns with a history link; Agents loads 100
  threads and labels absent parents. No remote hosting or desktop packaging.

Architecture and maintenance: [HANDOFF.md](HANDOFF.md),
[product API/design notes](docs/product.md).
