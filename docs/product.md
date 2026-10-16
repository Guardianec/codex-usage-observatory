# Product API and design notes

The original domain, adapter, ingestion, schema and aggregate service are unchanged.
Product queries aggregate SQL and pass every token sum through domain.Usage.

## Design system

Graphite dark workspace, mint activity/input, warm ochre output; warm-white light
workspace with sage navigation and dark green/brown data. Bundled IBM Plex Sans
and Mono. Compact 4/8 px spacing, 3–5 px radii, divider/typographic hierarchy.

Current turn is the primary readout. Distributions, event traces and daily bars have
distinct jobs; cache/reasoning stay nested. Charts provide exact hover/arrow-key
values and accessible tables. Motion is limited to brief CSS control transitions
with reduced-motion support. No scroll interception or external font/CDN requests.

## API

Product filters: start/end (timezone required, UTC [start,end)), project_id, model,
effort, status, session_id, task_id, root_session_id, search. Filters combine with
AND. Search matches turn/thread ID, project basename and model using bound SQL.
Unknown model filter is `__unknown__`; unknown project is `unknown`.

| Route | Response / controls |
|---|---|
| GET `/api/analytics` | summary, daily, daily_truncated, projects, models, efforts, recent, expensive, active, latest, cost, coverage, range_semantics |
| GET `/api/history` | items/total/page/limit; page ≥1, limit 1–100 (default 25); sort/direction |
| GET `/api/requests` | items/total/page/limit; default 50, max 100; newest first |
| GET `/api/timeline` | items/bucket_seconds; normalized usage + cumulative_tokens/tokens_per_minute |
| GET `/api/session-history` | thread summary pages; default 25, max 100; own usage only |
| GET `/api/task-detail` | requires session_id + task_id; task/cost/baselines(global,project,model) |
| GET `/api/export` | kind tasks/daily → CSV; statistics → analytics JSON; shared filters |
| GET `/api/settings` | thresholds, prices, runtime source/database/adapter/binding/interval |
| POST `/api/settings` | complete validation before atomic local replacement |

Sorts: started_at, total_tokens, input_tokens, cached_input_tokens, output_tokens,
request_count, duration_seconds, model, project; direction asc/desc. Bad filters,
sorts/ranges return 400; missing detail 404; storage failure 503; foreign origin 403.
Original API/SSE endpoints remain compatible. No raw content or stack traces.

Usage includes input, cached, uncached, output, reasoning, total and request_count.
Group statistics add task_count, measured_tasks, median/average_tokens,
median/average_duration_seconds, completed_turn_seconds. Empty medians are null.
Model statistics use that model's contribution to each turn; duration remains
whole-turn time including tools, waiting and other models. tokens_per_turn_minute
uses only turns with known positive duration. Project top_model uses actual token
contributions. These comparisons do not establish model quality or causation.

Active contains the latest eight last-known-running turns across all time. Unknown
zero-response turns are represented separately based on their start time. Timeline
points adapt to the observed span (~120, minimum minute), preserve idle gaps and
compute cumulative values server-side. Daily chart data is UTC, zero-filled, limited
to latest 730 days with daily_truncated; full-range daily exports are not chart-limited.

## Preferences and pricing

Defaults: 5M tokens, 100 responses, 60 minutes, 3× median. Warning severity is
elevated at 1× a threshold, high at 2×, critical at 3×. The strongest relative reason
is displayed. No notifications or automatic Codex control are performed.

Rates: `{model,effective_date,uncached_input_per_million,cached_input_per_million,
output_per_million}`. Exact-model/newest eligible UTC date uses the original Decimal
estimator. Finite nonnegative USD rates, valid dates and unique model/date pairs
are required. Cost shape: amount (string or null), covered_requests, total_requests,
complete, currency, basis. Partial coverage is always explicit.

POST requires application/json, ≤64 KiB and an exact same-origin localhost Origin.
No CORS. UI preferences use localStorage `observatory.theme`, `.landing`, `.time`.
Server settings is settings.json beside the DB. Runtime paths are deliberately
shown only in the local settings view and excluded from exports.

## Performance / boundaries

Browser receives grouped summaries, bounded request/task pages and timelines rather
than raw archives. SSE invalidations are coalesced; clients refetch and reconnect.
Task medians/sorts currently operate on grouped rows server-side. Extreme archives
may justify SQL-native percentile/pagination work after measurement. Whole-period
sums inspect normalized rows; unchanged ingestion still reparses zero archive bytes.
No speculative preaggregation, cloud deployment or destructive rebuild was added.
