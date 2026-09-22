# Fixture judgment offline

Fixture judgment offline runs the staged judgment pipeline (blind evidence reader, claim-visible judge, D0 citation auditor, reconciler, claim-card renderer) on a hand-built fixture without calling a model.

## Sub-features

- `fixture-complete` drives `tests/fixtures/judgment/complete.json` to a staged verdict JSON.
- `fixture-missing-citation` can exercise the missing-citation fixture the same way.
- `fixture-offline-seal` seals the reader payload before the claim-visible judge; no retrieval index is built.

## How to get to it (user POV)

- Run `PYTHONPATH=src python3 -m validator.fixture_pipeline --fixture <path> --output <path>` without `--live`.

## Driving it with the shell

Preconditions:

- Doctor `offline_ready=yes`.
- Fixture file present (default: `tests/fixtures/judgment/complete.json`).
- LM Studio is not required.

- **Prepare evidence dir.** Run `mkdir -p artifacts/verify-mavs/fixture-judgment`.
- **Run offline pipeline.** Run `PYTHONPATH=src python3 -m validator.fixture_pipeline --fixture tests/fixtures/judgment/complete.json --output artifacts/verify-mavs/fixture-judgment/complete_verdict.json`. Exit code `0`.
- **Inspect verdict.** Confirm the output JSON exists and includes staged judgment / report fields for the fixture claim.
- **Proof.** Save stdout/stderr and exit code to `artifacts/verify-mavs/fixture-judgment/transcript.txt` beside the verdict file.

## Gotchas

- Offline runs use deterministic lexical rules; they do not prove live prompt behavior.
- `--config`, `--base-url`, and `--model-id` are only valid with `--live`.
- Fixture claim ids are synthetic `scifact:N` shapes and are not corpus-lock ids.
