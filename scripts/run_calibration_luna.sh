#!/usr/bin/env bash
# Calibration-split run for the API model family: B1 on the 100 calibration
# claims. The temperature is fitted here and evaluated on the development and
# held-out samples (scripts/paper/make_calibration.py).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYBIN="${MAVS_PYTHON:-$ROOT/.venv-mavs/bin/python}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

"$PYBIN" -m validator.baselines \
  --config configs/baseline/b1.yaml \
  --live --split calibration --limit 100 \
  --workers 8 \
  --output artifacts/calibration/b1_luna/predictions.jsonl \
  --run-sidecar artifacts/calibration/b1_luna/run.json
