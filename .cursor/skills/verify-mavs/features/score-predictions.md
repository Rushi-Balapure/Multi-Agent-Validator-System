# Score predictions

Score predictions reads a B2 `predictions.jsonl`, computes native SciFact label precision/recall/F1 and false-endorsement metrics, and writes a metrics JSON citing `run_id` and formula ids from the metric contract.

## Sub-features

- `score-fixture` scores the checked-in fixture with an explicit `--run-id`.
- `score-join-gold` copies gold from a locked split when rows lack `label_gold`.
- `score-sidecar` resolves `run_id` from a run sidecar when `--run-id` is omitted.

## How to get to it (user POV)

- Run `PYTHONPATH=src python3 -m evaluation.score_predictions` with `--predictions` and `--output`.
- For paper tables, write under `docs/paper-assets/tables/` when intentionally checking in results.

## Driving it with the shell

Preconditions:

- Doctor `offline_ready=yes` (fixture path needs no SciFact raw).
- For `--join-gold development`, SciFact must be bootstrapped.

- **Score fixture.** Run `mkdir -p artifacts/verify-mavs/score` then `PYTHONPATH=src python3 -m evaluation.score_predictions --predictions src/evaluation/fixtures/b2_predictions.jsonl --run-id fixture-b2-score-001 --output artifacts/verify-mavs/score/b2_fixture_metrics.json`. Exit code `0`. Stdout mentions `run_id=fixture-b2-score-001`.
- **Confirm metrics file.** Open `artifacts/verify-mavs/score/b2_fixture_metrics.json` and check `run_id`, `n_scored`, and native / false-endorsement metric blocks. Shape should align with `src/evaluation/fixtures/b2_metrics_expected.json`.
- **Optional join-gold on a dry-run artifact.** After a dry-run produced predictions, run with `--run-sidecar` and `--join-gold development` into `artifacts/verify-mavs/score/b2_dry_run_metrics.json`.
- **Proof.** Keep the metrics JSON and a `transcript.txt` under `artifacts/verify-mavs/score/`.

## Gotchas

- Official test split is refused for gold join.
- Do not score a predictions file that mixes mock and live `inference_mode` rows.
- `artifacts/` is gitignored; durable paper copies go under `docs/paper-assets/tables/`.
- Fixture `fixture-b2-score-001` is a 10-row hand check, not a dry-run of the live n=20 development column.
