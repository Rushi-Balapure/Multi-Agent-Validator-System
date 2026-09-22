# MAVS CLI verification map

This directory is the maintained source for verifying the user-facing CLI behavior of Multi-Agent-Validator-System. Read this index before driving, then use the matching feature file as the recipe.

## Baseline preconditions

- Work from the repository root (contains `data/`, `configs/`, `src/`, `manifests/`).
- Python 3.11+ with project deps: `uv pip install -e ".[dev]"` or `python3 -m pip install -e ".[dev]"`.
- Export `PYTHONPATH=src` (or prefix every module command).
- Run `bash .cursor/skills/verify-mavs/helpers/doctor.sh` and require `offline_ready=yes`.
- SciFact pin files must exist at `data/pins/scifact/PIN.json` and `LOCKED.json`.
- Live features additionally require `lmstudio_1234=up` on `http://127.0.0.1:1234/v1`.
- Proof artifacts go under `artifacts/verify-mavs/`. Never invent a browser or web UI.

## Driving conventions

- Start every recipe from the baseline state unless its preconditions say otherwise.
- Treat every command as literal. Keep quoted paths and flags unchanged.
- Drive through plain shell module invocations (`python3 -m …`) or `bash scripts/retrieval_smoke.sh`.
- Prefer writing verify outputs under `artifacts/verify-mavs/<feature>/` so proof stays separate from default product artifact paths.
- Restore nothing destructive after a mutation of gitignored artifacts; retain proof files during cleanup.

## Proof and skip reporting

- CLI proof includes the command, stdout, stderr, exit code, and any files written.
- Record the feature ID and entry point used with every artifact.
- Report an unreachable path with the attempted command and the unmet precondition.
- Do not report a skipped live entry point as verified through dry-run or offline paths.
- Offline proof of one feature is enough for skill self-check; a full pass drives every mapped offline feature.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing the user-visible behavior. It then uses exactly four H2 sections in this order.

1. `Sub-features` lists short IDs with one line for each behavior.
2. `How to get to it (user POV)` lists every user entry point.
3. `Driving it with the shell` starts with `Preconditions:` and uses labeled bullets that pair each user action with an exact command and observable result.
4. `Gotchas` lists traps that can waste or invalidate a verification run.

Keep implementation details out of the map. Name only user paths, stable handles, required state, commands, and observable proof.

## Features

- [Bootstrap SciFact](./bootstrap-scifact.md) downloads and verifies the pinned corpus.
- [Same-evidence B2 dry-run](./same-evidence-b2-dry-run.md) runs the offline mock baseline.
- [Score predictions](./score-predictions.md) scores fixture or run predictions JSONL.
- [Fixture judgment offline](./fixture-judgment-offline.md) runs the staged judgment pipeline without a model.
- [Retrieval BM25 smoke](./retrieval-bm25-smoke.md) indexes twice and gathers the fixed ten-claim bundle.
- [Live B2](./live-b2.md) (optional) calls LM Studio when doctor finds `:1234`.
- [Live fixture judgment](./live-fixture.md) (optional) live D1 judgment when doctor finds `:1234`.
