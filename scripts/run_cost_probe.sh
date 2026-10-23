#!/usr/bin/env bash
# Per-claim cost probe.
#
# The development runs were resumed across several invocations because of
# transport failures, and each invocation writes its own usage meter, so the
# aggregate token count of a resumed run is not recoverable from its sidecar.
# This script measures the same two primary conditions in a single invocation
# on a fixed 50-claim sample, for both model families, with the same configs
# and prompts. The numbers in Table 11 come from these sidecars.
#
# Usage:
#   scripts/run_cost_probe.sh luna        # API family
#   scripts/run_cost_probe.sh minimax     # OpenCode family (needs the bridge)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FAMILY="${1:?usage: run_cost_probe.sh <luna|minimax>}"
PYBIN="${MAVS_PYTHON:-$ROOT/.venv-mavs/bin/python}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export OPENAI_API_KEY=""
export OPENAI_MODEL=""

SAMPLE="data/manifests/cost_probe_50.json"
case "$FAMILY" in
  luna)
    OUT="artifacts/cost_probe/luna"
    BASE_URL="${MAVS_BASE_URL:-https://api.openai.com/v1}"
    MODEL_ID="${MAVS_MODEL_ID:-gpt-6-luna}"
    export OPENAI_API_KEY="${OPENAI_API_KEY_REAL:-${OPENAI_API_KEY:-}}"
    WORKERS="${MAVS_WORKERS:-8}"
    ;;
  minimax)
    OUT="artifacts/cost_probe/minimax"
    BASE_URL="${MAVS_BASE_URL:-http://127.0.0.1:8801/v1}"
    MODEL_ID="${MAVS_MODEL_ID:-opencode/minimax-m3.1-flash-free}"
    WORKERS="${MAVS_WORKERS:-2}"
    ;;
  *)
    echo "unknown family: $FAMILY" >&2
    exit 2
    ;;
esac

mkdir -p "$OUT/B2" "$OUT/V"

"$PYBIN" -m validator.same_evidence.runner \
  --config configs/baseline/same_evidence_b2.yaml \
  --live --limit 50 --claim-ids-file "$SAMPLE" \
  --base-url "$BASE_URL" --model-id "$MODEL_ID" \
  --workers "$WORKERS" \
  --output "$OUT/B2/predictions.jsonl" \
  --run-sidecar "$OUT/B2/run.json"

"$PYBIN" -m validator.validator_v \
  --config configs/validator_v/development.yaml \
  --gather --live --limit 50 --claim-ids-file "$SAMPLE" \
  --base-url "$BASE_URL" --model-id "$MODEL_ID" \
  --workers "$WORKERS" \
  --output "$OUT/V/predictions.jsonl" \
  --run-sidecar "$OUT/V/run.json"

echo "cost probe for $FAMILY written under $OUT"
