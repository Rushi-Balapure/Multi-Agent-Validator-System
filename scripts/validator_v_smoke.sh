#!/usr/bin/env bash
# Offline Stack V smoke: fixture-report dry-run writes predictions.jsonl and run.json.
# No GPU, no LM Studio, no SciFact download.
# From the repo root: bash scripts/validator_v_smoke.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
export PYTHONPATH="${root}/src${PYTHONPATH:+:$PYTHONPATH}"
# Honour the caller's interpreter so a virtualenv that holds the dependencies
# can run this script without them also being installed for bare python3.
PYBIN="${MAVS_PYTHON:-python3}"

out="${VALIDATOR_V_SMOKE_OUT:-artifacts/validator_v_smoke}"
mkdir -p "$out"
predictions="${out}/predictions.jsonl"
sidecar="${out}/run.json"

"$PYBIN" -m validator.validator_v \
  --config configs/validator_v/development.yaml \
  --dry-run \
  --output "$predictions" \
  --run-sidecar "$sidecar"

"$PYBIN" - "$predictions" "$sidecar" <<'PY'
import json
import sys
from pathlib import Path

predictions = Path(sys.argv[1])
sidecar_path = Path(sys.argv[2])
rows = [json.loads(line) for line in predictions.read_text(encoding="utf-8").splitlines() if line.strip()]
if not rows or len(rows) > 20:
    raise SystemExit(f"validator v smoke: expected 1 to 20 rows, got {len(rows)}")
labels = {"SUPPORT", "REFUTE", "NEI"}
four = {"supported", "contradicted", "unaddressed", "underdetermined"}
for row in rows:
    if row.get("method_id") != "V" or row.get("adaptation") != "V":
        raise SystemExit(f"validator v smoke: method_id/adaptation {row.get('method_id')!r}")
    if row.get("label") not in labels:
        raise SystemExit(f"validator v smoke: label {row.get('label')!r} is outside SUPPORT/REFUTE/NEI")
    if row.get("label_4way") not in four:
        raise SystemExit(f"validator v smoke: label_4way {row.get('label_4way')!r}")
    if row.get("inference_mode") != "mock":
        raise SystemExit(f"validator v smoke: inference_mode {row.get('inference_mode')!r}")
    if not str(row.get("claim_id", "")).startswith("scifact:"):
        raise SystemExit(f"validator v smoke: claim_id {row.get('claim_id')!r}")
sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
if sidecar.get("method_id") != "V" or sidecar.get("inference_mode") != "mock":
    raise SystemExit("validator v smoke: sidecar method_id or inference_mode")
if sidecar.get("n_predictions") != len(rows):
    raise SystemExit("validator v smoke: n_predictions does not match the jsonl")
run = sidecar.get("run") or {}
if not run.get("run_id") or run.get("split") != "development":
    raise SystemExit("validator v smoke: run sidecar is missing run_id or development split")
print(f"validator v smoke OK n={len(rows)} run_id={run['run_id']}")
PY
