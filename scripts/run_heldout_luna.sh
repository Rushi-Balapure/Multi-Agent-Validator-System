#!/usr/bin/env bash
# One frozen held-out 300 run. Requires docs/freeze.json and --frozen-final.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYBIN="${MAVS_PYTHON:-python3}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

if [[ ! -f docs/freeze.json ]]; then
  echo "docs/freeze.json is missing; run scripts/write_freeze.py" >&2
  exit 2
fi

echo "B2 held-out"
"$PYBIN" -m validator.same_evidence.runner \
  --config configs/baseline/same_evidence_b2.yaml \
  --live --limit 300 --split held_out_local_eval --frozen-final \
  --output artifacts/held_out/b2/predictions.jsonl \
  --run-sidecar artifacts/held_out/b2/run.json

echo "V held-out"
"$PYBIN" -m validator.validator_v \
  --config configs/validator_v/development.yaml \
  --gather --live --limit 300 --split held_out_local_eval --frozen-final \
  --claim-ids-file data/manifests/heldout300.json \
  --output artifacts/held_out/v/predictions.jsonl \
  --run-sidecar artifacts/held_out/v/run.json

echo "held-out complete"
