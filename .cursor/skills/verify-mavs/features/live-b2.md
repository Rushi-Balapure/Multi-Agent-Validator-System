# Live B2

Live B2 runs the same-evidence baseline against a local OpenAI-compatible endpoint (default LM Studio on loopback `:1234`) and records `inference_mode=live` on prediction rows and the run sidecar.

## Sub-features

- `live-b2-limit` runs a small `--limit` against the live endpoint.
- `live-b2-endpoint` uses loopback or RFC1918 `base_url` only; public hosts are refused.
- `live-b2-mode` labels successful rows/sidecar as `live`.

## How to get to it (user POV)

- With LM Studio serving the configured model, run `PYTHONPATH=src python3 -m validator.same_evidence.runner` with `--live`.

## Driving it with the shell

Preconditions:

- Doctor reports `lmstudio_1234=up` / `live_ready=yes`.
- SciFact bootstrapped.
- Default config model id `qwen2.5-coder-1.5b-instruct` is loaded in LM Studio (or override via config).

- **Skip gate.** If `curl` to `http://127.0.0.1:1234/v1/models` is not `200`, stop and report skipped with that precondition. Do not substitute a cloud URL.
- **Live run limit 2.** Run `mkdir -p artifacts/verify-mavs/same-evidence-b2-live` then `PYTHONPATH=src python3 -m validator.same_evidence.runner --config configs/baseline/same_evidence_b2.yaml --live --limit 2 --output artifacts/verify-mavs/same-evidence-b2-live/predictions.jsonl --run-sidecar artifacts/verify-mavs/same-evidence-b2-live/run.json`.
- **Confirm live mode.** Predictions and sidecar show `inference_mode=live` on success.
- **Proof.** Keep transcript, predictions, and sidecar under `artifacts/verify-mavs/same-evidence-b2-live/`.

## Gotchas

- Dry-run success does not verify this feature.
- Public DNS / non-private addresses are refused, including redirects.
- Do not mix these live rows with mock rows before scoring.
