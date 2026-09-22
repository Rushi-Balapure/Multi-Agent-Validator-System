# Live fixture judgment

Live fixture judgment sends one fixture claim through the OpenAI-compatible local endpoint for D1 judgment. Parse failures become `execution_status: failed` and a non-zero exit; the model text is not turned into a scientific label by force.

## Sub-features

- `live-fixture-call` invokes `--live` with `configs/judgment/fixture_live.yaml` defaults.
- `live-fixture-policy` accepts loopback or RFC1918 `base_url` only.
- `live-fixture-fail-closed` exits `1` when the live response does not parse.

## How to get to it (user POV)

- With LM Studio up, run `PYTHONPATH=src python3 -m validator.fixture_pipeline --fixture <claim.json> --live`.

## Driving it with the shell

Preconditions:

- Doctor reports `lmstudio_1234=up` / `live_ready=yes`.
- Fixture path `tests/fixtures/judgment/complete.json` exists.

- **Skip gate.** If port `1234` models endpoint is not healthy, report skipped. Do not open public hosts.
- **Live fixture.** Run `mkdir -p artifacts/verify-mavs/fixture-judgment` then `PYTHONPATH=src python3 -m validator.fixture_pipeline --fixture tests/fixtures/judgment/complete.json --live --output artifacts/verify-mavs/fixture-judgment/complete_verdict_live.json`.
- **Observe outcome.** Exit `0` with a written verdict on success; exit `1` with failed execution status when the live response does not parse — capture that as evidence of fail-closed behavior when it happens.
- **Proof.** Keep transcript and output JSON under `artifacts/verify-mavs/fixture-judgment/`.

## Gotchas

- Pytest does not pass `--live`; this feature is a manual/agent CLI drive.
- Offline fixture success does not verify this feature.
- `--config` / `--base-url` / `--model-id` without `--live` is an error.
