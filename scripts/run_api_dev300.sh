#!/usr/bin/env bash
# API model family on the frozen development 300. Same configs, prompts,
# corpus and claim sample as the second family, and the same retry policy for
# requests that fail for transport or parse reasons.
#
# The held-out split is NOT run here. It is executed once under
# docs/freeze.json by scripts/run_heldout_luna.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYBIN="${MAVS_PYTHON:-$ROOT/.venv-mavs/bin/python}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"

SAMPLE="data/manifests/dev300_seed42.json"
OUT="${MAVS_OUT:-artifacts/api/dev300}"
WORKERS="${MAVS_WORKERS:-8}"
ATTEMPTS="${MAVS_ATTEMPTS:-4}"

mkdir -p "$OUT"

run_with_retries() {
  local predictions="$1"
  shift
  local attempt=1
  while [ "$attempt" -le "$ATTEMPTS" ]; do
    "$@" || true
    if ! "$PYBIN" scripts/paper/drop_failed_rows.py "$predictions" | grep -q "dropped"; then
      return 0
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -le "$ATTEMPTS" ]; then
      echo "retrying failed rows (attempt $attempt of $ATTEMPTS)"
      sleep 15
    fi
  done
  echo "WARNING: $predictions still has failed rows after $ATTEMPTS attempts"
}

run_v() {
  run_with_retries "$OUT/v/predictions.jsonl" \
    "$PYBIN" -m validator.validator_v \
    --config configs/validator_v/development.yaml \
    --gather --live --limit 300 --claim-ids-file "$SAMPLE" \
    --workers "$WORKERS" \
    --output "$OUT/v/predictions.jsonl" \
    --run-sidecar "$OUT/v/run.json"
}

run_b2() {
  run_with_retries "$OUT/b2/predictions.jsonl" \
    "$PYBIN" -m validator.same_evidence.runner \
    --config configs/baseline/same_evidence_b2.yaml \
    --live --limit 300 --claim-ids-file "$SAMPLE" \
    --workers "$WORKERS" \
    --output "$OUT/b2/predictions.jsonl" \
    --run-sidecar "$OUT/b2/run.json"
}

run_baseline() {
  local adaptation="$1" config="$2"
  run_with_retries "$OUT/$adaptation/predictions.jsonl" \
    "$PYBIN" -m validator.baselines \
    --config "$config" \
    --live --limit 300 --claim-ids-file "$SAMPLE" \
    --workers "$WORKERS" \
    --output "$OUT/$adaptation/predictions.jsonl" \
    --run-sidecar "$OUT/$adaptation/run.json"
}

echo "=== API dev-300: V ==="
run_v
echo "=== API dev-300: B2 ==="
run_b2
echo "=== API dev-300: B1 ==="
run_baseline B1 configs/baseline/b1.yaml
echo "=== API dev-300: B3 ==="
run_baseline B3 configs/baseline/b3.yaml
echo "=== API dev-300: O ==="
run_baseline O configs/baseline/oracle.yaml
echo "=== API dev-300: B0 ==="
run_baseline B0 configs/baseline/b0.yaml
echo "api dev300 complete"
