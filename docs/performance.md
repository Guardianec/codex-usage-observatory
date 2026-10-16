# Performance sanity check

Python 3.13.1, Windows, 2026-10-16. Synthetic, content-free fixtures.

```json
{
  "sessions": 250,
  "responses": 10001,
  "source_bytes": 52426418,
  "cold_seconds": 4.108,
  "warm_seconds": 0.095,
  "warm_parsed_bytes": 0,
  "append_seconds": 0.1,
  "append_parsed_lines": 1,
  "aggregate_seconds": 0.0029,
  "product_analytics_seconds": 0.0922,
  "product_payload_bytes": 16070,
  "python_peak_mib": 24.58
}
```

Cold scan includes tracemalloc overhead. Memory is traced Python allocations, not total process RSS or SQLite cache. Includes a 20 MB oversized line and 250 100 KB content lines. Warm scan stats files without parsing unchanged sources. Append scan reads one new record plus a 4 KB checkpoint anchor. Discovery is O(files) every two seconds; no archive contents are rescanned. Timestamp/model/task/root indexes support filtered queries; whole-history sums necessarily scan stored response rows. Reproduce with `python -m scripts.benchmark`.
