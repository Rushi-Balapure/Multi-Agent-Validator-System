# Same-evidence B2 dry-run

Same-evidence B2 dry-run runs the named B2 baseline over SciFact development claims using the documented offline mock: neutral question, isolated reader over D0 citations, compare step, without opening a socket to LM Studio.

## Sub-features

- `b2-dry-limit` runs a bounded claim count via `--limit`.
- `b2-dry-artifacts` writes predictions JSONL and a run sidecar under a chosen output path.
- `b2-dry-mock` records mock/dry-run inference mode and does not call `:1234`.

## How to get to it (user POV)

- From the repository root with SciFact bootstrapped, run `PYTHONPATH=src python3 -m validator.same_evidence.runner` with `--dry-run`.
- After `pip install -e .`, the console script `same-evidence-baseline` accepts the same flags.

## Driving it with the shell

Preconditions:

- Doctor `offline_ready=yes`.
- SciFact raw present (`retrieval_ready=yes` / successful bootstrap).
- Config `configs/baseline/same_evidence_b2.yaml` exists.

- **Prepare evidence dir.** Run `mkdir -p artifacts/verify-mavs/same-evidence-b2`.
- **Dry-run limit 2.** Run `PYTHONPATH=src python3 -m validator.same_evidence.runner --config configs/baseline/same_evidence_b2.yaml --dry-run --limit 2 --output artifacts/verify-mavs/same-evidence-b2/predictions.jsonl --run-sidecar artifacts/verify-mavs/same-evidence-b2/run.json`. Exit code `0`.
- **Inspect predictions.** Confirm `predictions.jsonl` has exactly two non-empty JSON lines with `claim_id` values and predicted labels in `SUPPORT` / `REFUTE` / `NEI`.
- **Inspect sidecar.** Confirm `run.json` exists and reflects dry-run/mock inference (no successful live call required).
- **Proof.** Save command transcript to `artifacts/verify-mavs/same-evidence-b2/transcript.txt` next to the two artifact files.

## Gotchas

- Passing both `--dry-run` and `--live` fails; use one mode.
- Default config points at LM Studio for live runs; dry-run still works when `:1234` is down.
- Missing D0 joins exit `2`; empty SciFact evidence objects do not.
- Do not score a file that mixes mock and live rows.
