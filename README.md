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
