#!/usr/bin/env bash
# MiniMax M3.1 Flash on the frozen development 300. Same configs, prompts,
# corpus and claim sample as the API-family runs; only the endpoint and model
# id differ (--base-url / --model-id).
#
# Requires the OpenCode bridge on loopback:
#   OPENCODE_SERVER_PASSWORD=<secret> python3 tools/opencode_bridge.py --port 8801 \
#     --agent mavs-judge --location tools/opencode_agent
#
# OPENAI_API_KEY and OPENAI_MODEL are cleared so the repository's
# apply_openai_env helper does not redirect the run to api.openai.com.
#
# The hosted free tier throttles bursts, so the runner keeps a small worker
# count and retries the claims whose request failed for transport reasons.
set -euo pipefail

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
ATTEMPTS="${MAVS_ATTEMPTS:-4}"

mkdir -p "$OUT"

# run_with_retries <predictions-path> <command...>
#
# Runs the command. If some rows ended with a failed execution status (the
# hosted endpoint refused or throttled the request), those rows are dropped
# so the next attempt re-claims exactly those claims, and the command is run
# again. Up to ATTEMPTS attempts.
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
      sleep 30
    fi
  done
  echo "WARNING: $predictions still has failed rows after $ATTEMPTS attempts"
}

run_b2() {
  run_with_retries "$OUT/b2/predictions.jsonl" \
    "$PYBIN" -m validator.same_evidence.runner \
    --config configs/baseline/same_evidence_b2.yaml \
    --live --limit 300 --claim-ids-file "$SAMPLE" \
    --base-url "$BASE_URL" --model-id "$MODEL_ID" \
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
    --base-url "$BASE_URL" --model-id "$MODEL_ID" \
    --workers "$WORKERS" \
    --output "$OUT/$adaptation/predictions.jsonl" \
    --run-sidecar "$OUT/$adaptation/run.json"
}

run_v() {
  run_with_retries "$OUT/v/predictions.jsonl" \
    "$PYBIN" -m validator.validator_v \
    --config configs/validator_v/development.yaml \
    --gather --live --limit 300 --claim-ids-file "$SAMPLE" \
    --base-url "$BASE_URL" --model-id "$MODEL_ID" \
    --workers "$WORKERS" \
    --output "$OUT/v/predictions.jsonl" \
    --run-sidecar "$OUT/v/run.json"
}

echo "=== MiniMax dev-300: V (independent retrieval + staged judgment) ==="
run_v
echo "=== MiniMax dev-300: B2 (same-evidence baseline) ==="
run_b2
echo "=== MiniMax dev-300: B1 ==="
run_baseline B1 configs/baseline/b1.yaml
echo "=== MiniMax dev-300: B3 ==="
run_baseline B3 configs/baseline/b3.yaml
echo "=== MiniMax dev-300: O (evidence oracle) ==="
run_baseline O configs/baseline/oracle.yaml
echo "=== MiniMax dev-300: B0 (prior knowledge) ==="
run_baseline B0 configs/baseline/b0.yaml
echo "=== MiniMax calibration split: B1 (temperature fit) ==="
run_with_retries artifacts/minimax/calibration/b1/predictions.jsonl \
  "$PYBIN" -m validator.baselines \
  --config configs/baseline/b1.yaml \
  --live --split calibration --limit 100 \
  --base-url "$BASE_URL" --model-id "$MODEL_ID" \
  --workers "$WORKERS" \
  --output artifacts/minimax/calibration/b1/predictions.jsonl \
  --run-sidecar artifacts/minimax/calibration/b1/run.json
echo "minimax dev300 complete"
