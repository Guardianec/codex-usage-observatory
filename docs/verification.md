# Verification and private reports

The accounting implementation was reconciled against local Codex response, task,
and thread counters. All checked recorded usage and cumulative deltas matched.
Detailed machine-specific figures and identifiers are intentionally not published.

Run `python -m scripts.verify_local` on your own computer to reproduce the check.
The resulting numeric report is written to `.local/reports/verification.md`, which
is ignored by Git. The verifier reads Codex telemetry without modifying it.
An explicit `--output` override can contain private usage information; keep such
reports in an ignored local directory.

Committed fixtures use synthetic IDs, paths and token values while retaining the
observed event structure. For example, input 1,000, cached 200, output 100 and
reasoning 20 means uncached 800 and total 1,100. Reasoning is already in output.
The three-response fixture sums to input 6,000, cached 4,200, uncached 1,800,
output 600, reasoning 170 and total 6,600. These figures are test examples, not
records of anyone's Codex usage.

Checks: `python -m unittest discover -v` and `npm test`.
