# Local telemetry investigation

Inspected read-only on 2026-10-16. Installed `codex-cli 0.163.0-alpha.10.2`;
rollouts also contain `0.162.0-alpha.17.2`. CLI version/help attempted its own
temporary-directory housekeeping, denied by the sandbox; no log files were changed.
`codex exec --help` confirms `--json`, but no paid model request was launched:
stdout exec events are a separate, unverified transport and are not this adapter's input.

Sources: `%USERPROFILE%/.codex/sessions/**/*.jsonl` and
`archived_sessions/**/*.jsonl`. Machine-specific inventory and usage figures are intentionally omitted from the
shared documentation.
Configuration was inspected only for model and reasoning effort; auth files were not read.
The local SQLite databases and session index are unnecessary for this adapter.

## Observed schema

Envelope: `timestamp`, `type`, `payload`. Types: `session_meta`, `turn_context`,
`token_usage_record`, `event_msg`, `response_item`, `world_state`, `compacted`,
`retained_context`. Content-bearing events are ignored, never persisted.

`token_usage_record.payload` contains `response_id`, `thread_id`, `session_id`,
`turn_id`, `root_turn_id`, `usage`, `turn_token_usage`, `thread_token_usage`.
All three usage objects contain `input_tokens`, `cached_input_tokens`,
`cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`, `total_tokens`.
`usage` is per response. The other two objects are cumulative by turn and thread.
In the inspected sample every turn/thread counter delta exactly matched `usage`.
Every record satisfied total = input + output, cached <= input, reasoning <= output;
all cache-write values were zero. Reasoning is treated as included in output;
cache hits are included in input. This is locally evidenced compatibility, not a
guarantee about future schemas. Nonzero cache writes are rejected until investigated.

`event_msg/token_count.info` has `total_token_usage`, `last_token_usage`, and
`model_context_window`; it repeats usage and can be null. Its `rate_limits` has
limit ID/name, primary/secondary used_percent, window_minutes, resets_at, credits
and plan metadata. These are account quota snapshots, not token-to-quota conversion.
The engine deliberately ignores these counters for accounting. Legacy files with
only token_count have unknown usage, not an invented request count.

## Identity and attribution

`session_meta.id` is the thread ID. **session_meta.session_id can instead identify
the root session shared by a parent and guardian children.** Store them separately.
`parent_thread_id` explicitly links guardian threads; `source.subagent.other` is
`guardian`, `thread_source` is `guardian_review`. Some metadata includes
`subagent_history_start_ordinal`; history is paginated. Inherited content is not usage.
No duplicated response IDs were found in the inspected snapshot. Nevertheless the
database deduplicates response IDs globally and detects conflicting copies.

`event_msg/task_started` supplies turn_id, root_turn_id and turn_attribution with
parent_turn_id, turn_trigger, initiating_agent_path. `task_complete` has turn_id,
timestamps/duration and optional error; `turn_aborted` is also supported defensively.
Turn IDs, not user-message counts, define tasks. Automatic guardian reviews and
remote triggers are tasks too; one user operation can span several turns. No exact
user-operation grouping beyond explicit root IDs is claimed. Missing lifecycle
events give an unknown status. An unclosed started turn is last-known running,
not proof that a process is still alive.

`turn_context` supplies turn_id, model, effort, cwd. Observed models:
gpt-6-astra (medium/high), gpt-6.1-sol (medium/high/xhigh), codex-auto-review (low).
These are observed identifiers, not an available-model catalog. Usage inherits the
latest matching turn context; absent context stays null. Context model can change
within a turn; each response stores its own observed model/effort.

Guardian child usage is directly attributable by its own thread_id and response_id.
Root session totals can include children without adding any cumulative counters.
Ordinary collaboration subagents, forks, retries with new response IDs and provider
billing were not observed sufficiently to claim complete attribution. Different
response IDs count as distinct recorded responses, not necessarily all network
attempts. Failed requests without usage are not counted. Zero means zero recorded
usage only; clients must show coverage/status alongside totals.

## Compatibility boundary

Adapter `rollout-v1` accepts the evidenced dedicated records, not arbitrary historical
Codex formats. Unknown events are ignored; malformed/unsupported records produce
content-free diagnostics. Counter mismatches are reported separately from accepted
per-response usage. Future schema changes require fixtures, investigation, and a
versioned migration/reimport decision. No heuristic cumulative fallback is mixed
with response accounting.
