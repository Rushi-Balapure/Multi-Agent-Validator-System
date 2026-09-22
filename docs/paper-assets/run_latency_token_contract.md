# Run latency and token fields

Eval Forge scores `F-latency-cost` from the shared Run record. Corpus Lock owns that record in `src/validator/schemas.py` (`Run`) and `schemas/mavs_run_record.schema.json`. This note records the gap. It does not add a second schema.

## Fields on Run today

- `tokens` is an object or null. The schema names no keys inside it. The same-evidence B2 runner writes `null`.
- `timestamps` is an object. The B2 runner writes `started_at` and `finished_at` as ISO-8601 strings. That pair is a start and a finish, not a latency distribution.

## Fields `F-latency-cost` needs

[F-latency-cost](formulas/F-latency-cost.md) asks for median and p95 end-to-end latency, warm versus cold cache, token counts, failures, cost per report and per claim, and peak memory when it is available. Run has no named field for those measurements.

## Ask for Corpus Lock and Arch Lead

Add named latency and token fields on Run, or publish the exact keys allowed inside `timestamps` and `tokens`, before any `F-latency-cost` cell is filled. Eval Forge will leave those cells empty until that contract exists. The bootstrap scaffold in `src/evaluation/bootstrap.py` stores the 2000-resample plan and does not emit intervals, latency totals, or token totals.
