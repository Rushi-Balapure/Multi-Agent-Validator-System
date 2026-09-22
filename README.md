# Multi-Agent-Validator-System

Status: scaffolding.

Reproducible inference-time validator for scientific conclusions, plus a research-paper draft. SciFact is the first corpus. A same-evidence baseline comes before the independent-retrieval validator.

- Research plan: [Validator_Agent_Two_Month_Research_Plan.pdf](Validator_Agent_Two_Month_Research_Plan.pdf)
- Implementation plan: [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md)
- Paper graphs and formula notes: [docs/paper-assets/](docs/paper-assets/)

## Same-evidence baseline (B2)

Named adaptation of research-plan B2: a template neutral question, an isolated reader over the claim's original citations (D0), then a compare step. Claims are loaded with `data.scifact_loader.load_split("development")`. Predictions are SciFact `SUPPORT` / `REFUTE` / `NEI` (`CONTRADICT` maps to `REFUTE`). The dry-run uses a documented mock and does not retrieve documents.

```bash
python3 -m pip install -e ".[dev]"
python3 -m data.pins.scifact.download_verify
python3 -m pytest tests/test_same_evidence_baseline.py -q
PYTHONPATH=src python3 -m validator.same_evidence.runner \
  --config configs/baseline/same_evidence_b2.yaml \
  --dry-run --limit 20 \
  --output artifacts/same_evidence_b2/predictions.jsonl \
  --run-sidecar artifacts/same_evidence_b2/run.json
```

## Phase-1 offline smoke

No GPU, no LM Studio, and no SciFact download. Dry-runs the B2 mock (`MockClient`, the client `--dry-run` selects) on a MIT synthetic claim (`tests/fixtures/phase1/example_claim.json`), then scores the committed Eval Forge fixture with `evaluation.score_predictions`. If pinned raw files are already under `data/raw/scifact/`, the script also runs `validator.same_evidence.runner --dry-run --limit 1`. It never downloads.

```bash
bash scripts/phase1_smoke.sh
```

Writes `artifacts/phase1_smoke/predictions.jsonl`, `run.json`, and `metrics.json` (gitignored). `PHASE1_SMOKE_OUT` overrides that directory.

## Stack V batch runner

Offline dry-run of the staged D0 ∪ D1 pipeline over the three report fixtures. The scored `label` is the reconciled four-way judgment mapped onto `SUPPORT` / `REFUTE` / `NEI` (`supported` → `SUPPORT`, `contradicted` → `REFUTE`, `unaddressed` and `underdetermined` → `NEI`). `label_4way` keeps the four-way token. At most 20 development claims are written. `method_id` is `V`.

```bash
PYTHONPATH=src python3 -m validator.validator_v \
  --config configs/validator_v/development.yaml \
  --dry-run \
  --output artifacts/validator_v/predictions.jsonl \
  --run-sidecar artifacts/validator_v/run.json
```

`--gather` is opt-in. It calls Retrieval Wing `gather(neutral_question, config, claim_id)` for development claim ids in B2 order (config `claim_ids`, or `--claim-ids`, or the first `--limit` locked development manifest ids) and does not pass gold D0. Offline smoke: `bash scripts/validator_v_smoke.sh`. Phase-3 Turing-Machine live gather (BM25 index + LM Studio `http://127.0.0.1:1234/v1`): `bash scripts/validator_v_phase3_gather_smoke.sh`. `VALIDATOR_V_SMOKE_OUT` / `VALIDATOR_V_PHASE3_OUT` override output directories.
