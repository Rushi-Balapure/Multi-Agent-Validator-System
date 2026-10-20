#!/usr/bin/env bash
# Completion pass for the second model family.
#
# The hosted free tier throttles bursts and refuses requests outright when a
# burst looks abusive, so a long run can finish with claims missing. The
# runner's resume re-claims exactly the missing claim ids, so this script
# simply repeats the run until every requested claim is present, dropping
# the rows whose request failed so that they are retried as well.
#
# The bridge should be started with a pacing interval, for example:
#   OPENCODE_SERVER_PASSWORD=<secret> python3 tools/opencode_bridge.py \
#     --port 8801 --agent mavs-judge --location tools/opencode_agent \
#     --min-interval 2.5
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYBIN="${MAVS_PYTHON:-$ROOT/.venv-mavs/bin/python}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENAI_API_KEY=""
export OPENAI_MODEL=""

BASE_URL="${MAVS_BASE_URL:-http://127.0.0.1:8801/v1}"
MODEL_ID="${MAVS_MODEL_ID:-opencode/minimax-m3.1-flash-free}"
SAMPLE="data/manifests/dev300_seed42.json"
OUT="${MAVS_OUT:-artifacts/minimax/dev300}"
WORKERS="${MAVS_WORKERS:-2}"
PASSES="${MAVS_PASSES:-12}"
TARGET="${MAVS_TARGET:-300}"

mkdir -p "$OUT"

complete() {
  local name="$1" predictions="$2"
  shift 2
  local pass=1
  while [ "$pass" -le "$PASSES" ]; do
    "$@" >/dev/null 2>&1 || true
    "$PYBIN" scripts/paper/drop_failed_rows.py "$predictions" >/dev/null 2>&1 || true
    local n=0
    if [ -f "$predictions" ]; then
      n="$(wc -l < "$predictions")"
    fi
    echo "[$name] pass $pass: $n/$TARGET rows"
    if [ "$n" -ge "$TARGET" ]; then
      echo "[$name] complete"
      return 0
    fi
    sleep 45
    pass=$((pass + 1))
  done
  echo "[$name] INCOMPLETE after $PASSES passes"
  return 1
}

complete "V" "$OUT/v/predictions.jsonl" \
  "$PYBIN" -m validator.validator_v \
  --config configs/validator_v/development.yaml \
  --gather --live --limit 300 --claim-ids-file "$SAMPLE" \
  --base-url "$BASE_URL" --model-id "$MODEL_ID" \
  --workers "$WORKERS" \
  --output "$OUT/v/predictions.jsonl" \
  --run-sidecar "$OUT/v/run.json"

complete "B2" "$OUT/b2/predictions.jsonl" \
  "$PYBIN" -m validator.same_evidence.runner \
  --config configs/baseline/same_evidence_b2.yaml \
  --live --limit 300 --claim-ids-file "$SAMPLE" \
  --base-url "$BASE_URL" --model-id "$MODEL_ID" \
  --workers "$WORKERS" \
  --output "$OUT/b2/predictions.jsonl" \
  --run-sidecar "$OUT/b2/run.json"

for pair in "B1 configs/baseline/b1.yaml" "B3 configs/baseline/b3.yaml" "O configs/baseline/oracle.yaml" "B0 configs/baseline/b0.yaml"; do
  set -- $pair
  complete "$1" "$OUT/$1/predictions.jsonl" \
    "$PYBIN" -m validator.baselines \
    --config "$2" \
    --live --limit 300 --claim-ids-file "$SAMPLE" \
    --base-url "$BASE_URL" --model-id "$MODEL_ID" \
    --workers "$WORKERS" \
    --output "$OUT/$1/predictions.jsonl" \
    --run-sidecar "$OUT/$1/run.json"
done

complete "B1-calibration" artifacts/minimax/calibration/b1/predictions.jsonl \
  "$PYBIN" -m validator.baselines \
  --config configs/baseline/b1.yaml \
  --live --split calibration --limit 100 \
  --base-url "$BASE_URL" --model-id "$MODEL_ID" \
  --workers "$WORKERS" \
  --output artifacts/minimax/calibration/b1/predictions.jsonl \
  --run-sidecar artifacts/minimax/calibration/b1/run.json

echo "minimax completion pass complete"
