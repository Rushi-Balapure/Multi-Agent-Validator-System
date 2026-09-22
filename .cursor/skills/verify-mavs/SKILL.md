---
name: verify-mavs
description: "Drive Multi-Agent-Validator-System (MAVS) as a CLI: SciFact bootstrap, BM25 retrieval smoke, same-evidence B2 dry-run/--live, score_predictions, and fixture judgment. Use when verifying MAVS behavior, proving offline CLI paths, or checking LM Studio live gates — never invent a web UI."
---

# Verify Multi-Agent-Validator-System (CLI)

Agent-facing control skill for this repo's **CLI surface**. There is no web UI. Drive short-lived Python module commands from the repository root with `PYTHONPATH=src`. Capture transcripts and artifact files under `artifacts/verify-mavs/`.

Read `.cursor/skills/verify-mavs/features/README.md` before a pass, then drive the matching feature file.

## Launch

This app is a short-lived CLI: there is no long-running server for the offline path. Launch means install deps once, bootstrap SciFact when needed, then run each drive in its own shell (or tmux pane for long BM25/smoke runs).

From the repository root (the directory that contains `data/`, `configs/`, `src/`, `manifests/`):

```bash
# Prefer uv when available; otherwise venv + pip.
uv venv .venv && source .venv/bin/activate && uv pip install -e ".[dev]"
# Fallback:
python3 -m venv .venv && source .venv/bin/activate && python3 -m pip install -e ".[dev]"

export PYTHONPATH=src
python3 -m data.bootstrap_scifact   # prints SMOKE OK then BOOTSTRAP OK
```

Ready when:

- `python3 -c "import pydantic, yaml, jsonschema"` succeeds
- `PYTHONPATH=src python3 -c "import validator.same_evidence.runner, evaluation.score_predictions"` succeeds
- Bootstrap ends with `BOOTSTRAP OK` (or doctor reports `corpus_raw=ok`)

Teardown: deactivate the venv if you created one. Do not delete `data/raw/scifact/` between drives in the same verification run (re-download is slow). Do not kill unrelated Python processes by name.

GPU is never required. Offline dry-run and fixture scoring need no LM Studio.

## Doctor

Run the shipped helper first whenever anything looks off:

```bash
bash .cursor/skills/verify-mavs/helpers/doctor.sh
```

Require:

- `deps=ok`, `imports=ok`, `corpus_pin=present`, `offline_ready=yes`
- For BM25 / `retrieval_smoke.sh`: `retrieval_ready=yes` (raw SciFact present and hash-matched)
- For live B2 or live fixture only: `lmstudio_1234=up` / `live_ready=yes`

Manual equivalents:

```bash
test -f data/pins/scifact/PIN.json
python3 -m data.pins.scifact.download_verify   # when data/raw/scifact exists
curl -s -o /dev/null -w '%{http_code}\n' --connect-timeout 1 http://127.0.0.1:1234/v1/models
# expect 200 only when LM Studio is serving; dry-run still works when this fails
```

If doctor says `live_ready=no`, skip `live-b2` and `live-fixture` features. Report them skipped with the unmet precondition. Do not invent cloud endpoints.

## Drive

All commands assume repository root and `export PYTHONPATH=src` (or prefix each command). Treat flags and paths as literal.

### Bootstrap SciFact

```bash
python3 -m data.bootstrap_scifact
```

Expect `SMOKE OK` then `BOOTSTRAP OK`. Non-zero exit means a pin/hash mismatch — report it; do not rewrite `PIN.json` / `LOCKED.json`.

### Same-evidence B2 dry-run (limit 2)

```bash
mkdir -p artifacts/verify-mavs/same-evidence-b2
PYTHONPATH=src python3 -m validator.same_evidence.runner \
  --config configs/baseline/same_evidence_b2.yaml \
  --dry-run --limit 2 \
  --output artifacts/verify-mavs/same-evidence-b2/predictions.jsonl \
  --run-sidecar artifacts/verify-mavs/same-evidence-b2/run.json
```

Expect exit 0, two JSONL rows, sidecar `inference_mode` consistent with mock/dry-run. No socket open to `:1234`.

### Same-evidence B2 live (optional)

Only when doctor reports `lmstudio_1234=up`:

```bash
PYTHONPATH=src python3 -m validator.same_evidence.runner \
  --config configs/baseline/same_evidence_b2.yaml \
  --live --limit 2 \
  --output artifacts/verify-mavs/same-evidence-b2-live/predictions.jsonl \
  --run-sidecar artifacts/verify-mavs/same-evidence-b2-live/run.json
```

Expect rows/sidecar with `inference_mode=live`. Default endpoint is `http://127.0.0.1:1234/v1` (`qwen2.5-coder-1.5b-instruct`).

### Score predictions (fixture)

```bash
mkdir -p artifacts/verify-mavs/score
PYTHONPATH=src python3 -m evaluation.score_predictions \
  --predictions src/evaluation/fixtures/b2_predictions.jsonl \
  --run-id fixture-b2-score-001 \
  --output artifacts/verify-mavs/score/b2_fixture_metrics.json
```

Expect exit 0 and a metrics JSON with `run_id=fixture-b2-score-001`. Compare shape to `src/evaluation/fixtures/b2_metrics_expected.json` when checking the fixture contract.

To score a dry-run/live artifact after bootstrap:

```bash
PYTHONPATH=src python3 -m evaluation.score_predictions \
  --predictions artifacts/verify-mavs/same-evidence-b2/predictions.jsonl \
  --run-sidecar artifacts/verify-mavs/same-evidence-b2/run.json \
  --join-gold development \
  --output artifacts/verify-mavs/score/b2_dry_run_metrics.json
```

Checked-in paper tables live under `docs/paper-assets/tables/` (`artifacts/` is gitignored).

### Fixture judgment pipeline (offline)

```bash
mkdir -p artifacts/verify-mavs/fixture-judgment
PYTHONPATH=src python3 -m validator.fixture_pipeline \
  --fixture tests/fixtures/judgment/complete.json \
  --output artifacts/verify-mavs/fixture-judgment/complete_verdict.json
```

Expect exit 0 and a staged verdict JSON. Offline path uses deterministic label policy; no model call.

### Fixture judgment live (optional)

Only when `lmstudio_1234=up`:

```bash
PYTHONPATH=src python3 -m validator.fixture_pipeline \
  --fixture tests/fixtures/judgment/complete.json \
  --live \
  --output artifacts/verify-mavs/fixture-judgment/complete_verdict_live.json
```

### BM25 retrieval smoke (when corpus present)

```bash
bash scripts/retrieval_smoke.sh
```

Expect byte-identical double index build, `artifacts/retrieval/dev10_bundles.jsonl` with the ten fixed claim ids, and a final `OK`. Copy proof snippets into `artifacts/verify-mavs/retrieval/` if you need them beside other verify evidence.

## Evidence

Proof directory for this skill: **`artifacts/verify-mavs/`** (gitignored with the rest of `artifacts/`).

Capture for every drive:

| Kind | What to keep |
| --- | --- |
| CLI transcript | Command, cwd, exit code, stdout, stderr → e.g. `artifacts/verify-mavs/<feature>/transcript.txt` |
| Predictions | `predictions.jsonl` + `run.json` sidecar when produced |
| Metrics | `*.json` from `evaluation.score_predictions` |
| Verdict | Fixture pipeline output JSON |
| Retrieval | Index/bundle paths under `artifacts/retrieval/` plus smoke `OK` line |
| Paper copies | Stable scored tables under `docs/paper-assets/tables/` when intentionally checked in |

Standards:

- Exercise the real CLI module entry points above, not internal setters.
- Record the action (exact command) and resulting files/exit code.
- For dry-run, confirm no live endpoint was required (doctor `live_ready=no` is fine; rows show mock/dry-run mode).
- Do not mix mock and live rows in one scored predictions file.
- GPU is out of scope; refuse instructions that require one.

## Cleanup

- Remove only scratch temps you created (`/tmp/mavs-*`, duplicate index copies the smoke script already deletes).
- **Do not delete** `artifacts/verify-mavs/` proof transcripts, predictions, metrics, or verdicts from the current run.
- **Do not delete** `docs/paper-assets/` or pin files.
- Leave `data/raw/scifact/` in place unless the user asked to reclaim disk; if you must reclaim, say so — the next bootstrap will re-download.
- Kill only processes this verification run started (e.g. a tmux session you opened for smoke). Never `pkill -f python` by name.

## Helpers

| Helper | Invocation |
| --- | --- |
| Doctor | `bash .cursor/skills/verify-mavs/helpers/doctor.sh` |

Feature recipes: `.cursor/skills/verify-mavs/features/`.

After the map drifts, use `/maintain-verification-skill` to re-audit this directory only.
