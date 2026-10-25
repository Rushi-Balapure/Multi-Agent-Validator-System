#!/usr/bin/env bash
# Multi-model sweep: B2 versus V on the frozen 30-claim subset.
#
# Four closed-weight models are served by the official API under a hard
# spend cap; seven free models are served by the loopback OpenCode bridge.
# Every model runs the same configs, prompts, corpus, and claim sample, and
# uses the same retry policy. Failed rows are dropped and re-claimed rather
# than turned into verdicts.
#
# Usage:
#   bash scripts/run_model_sweep.sh              # all models, resumable
#   bash scripts/run_model_sweep.sh astra sol    # selected model keys
#
# Environment:
#   MAVS_MAX_SPEND_USD   hard cap for the closed-weight models (default 4.60)
#   MAVS_SWEEP          output root (default artifacts/sweep)
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYBIN="${MAVS_PYTHON:-$ROOT/.venv-mavs/bin/python}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
SAMPLE="data/manifests/sweep30_seed42.json"
OUT="${MAVS_SWEEP:-artifacts/sweep}"
MAX_SPEND="${MAVS_MAX_SPEND_USD:-4.60}"
mkdir -p "$OUT"

# key | kind | model id | workers
MODELS=(
  "luna|closed|gpt-6-luna|4"
  "sol|closed|gpt-6-sol|4"
  "terra|closed|gpt-5.6-terra|4"
  "astra|closed|gpt-6-astra|3"
  "deepseek|open|opencode/deepseek-v4.1-flash-free|1"
  "glm|open|opencode/glm-5.3-flash-free|1"
  "flint|open|opencode/flint-40b-free|1"
  "beam|open|opencode/beam-free|1"
  "mimo|open|opencode/mimo-v2.6-flash-free|1"
  "nemotron|open|opencode/nemotron-3.5-super-vl-free|1"
  "pickle|open|opencode/big-pickle|1"
)

selected=("$@")

wanted() {
  local key="$1"
  [ ${#selected[@]} -eq 0 ] && return 0
  local item
  for item in "${selected[@]}"; do
    [ "$item" = "$key" ] && return 0
  done
  return 1
}

complete() {
  local file="$1"
  [ -f "$file" ] || return 1
  "$PYBIN" - "$file" <<'PY'
import json, sys
rows = [json.loads(line) for line in open(sys.argv[1], encoding="utf-8") if line.strip()]
ok = [r for r in rows if str(r.get("execution_status") or "ok") == "ok"]
raise SystemExit(0 if len(rows) >= 30 and len(ok) == len(rows) else 1)
PY
}

spend_so_far() {
  "$PYBIN" - "$OUT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1])
prices = {
    "gpt-6-astra": (1e-5, 5e-5),
    "gpt-6-sol": (2e-6, 1e-5),
    "gpt-5.6-terra": (2e-6, 1.2e-5),
    "gpt-6-luna": (1e-7, 5e-7),
}
total = 0.0
for sidecar in root.glob("*/*/run.json"):
    data = json.loads(sidecar.read_text())
    run = data.get("run") or {}
    price = prices.get(run.get("model_id"))
    tokens = run.get("tokens") or {}
    if not price or not tokens:
        continue
    total += tokens.get("prompt_tokens", 0) * price[0] + tokens.get("completion_tokens", 0) * price[1]
print(f"{total:.4f}")
PY
}

run_one() {
  local label="$1"
  local command="$2"
  local predictions="$3"
  local attempt=1
  while [ "$attempt" -le 4 ]; do
    eval "$command" || true
    if complete "$predictions"; then
      return 0
    fi
    "$PYBIN" scripts/paper/drop_failed_rows.py "$predictions" >/dev/null 2>&1 || true
    attempt=$((attempt + 1))
    if [ "$attempt" -le 4 ]; then
      echo "  retry $label (attempt $attempt of 4)"
      sleep 30
    fi
  done
  echo "  WARNING: $label still incomplete"
  return 1
}

for spec in "${MODELS[@]}"; do
  IFS="|" read -r key kind model workers <<<"$spec"
  wanted "$key" || continue

  b2="$OUT/$key/b2/predictions.jsonl"
  v="$OUT/$key/v/predictions.jsonl"
  if complete "$b2" && complete "$v"; then
    echo "== $key already complete"
    continue
  fi

  if [ "$kind" = "closed" ]; then
    set -a
    . ./.env
    set +a
    export OPENAI_MODEL="$model"
    base="https://api.openai.com/v1"
    spent="$(spend_so_far)"
    if "$PYBIN" -c "import sys; sys.exit(0 if float('$spent') >= float('$MAX_SPEND') else 1)"; then
      echo "== $key skipped: spend $spent has reached the cap $MAX_SPEND"
      continue
    fi
    echo "== $key ($model) closed, spent so far \$$spent"
  else
    export OPENAI_API_KEY=""
    export OPENAI_MODEL=""
    base="http://127.0.0.1:8801/v1"
    echo "== $key ($model) free bridge"
  fi

  mkdir -p "$OUT/$key/b2" "$OUT/$key/v"

  run_one "$key B2" \
    "'$PYBIN' -m validator.same_evidence.runner \
      --config configs/baseline/same_evidence_b2.yaml \
      --live --limit 30 --claim-ids-file '$SAMPLE' \
      --workers $workers \
      --output '$b2' --run-sidecar '$OUT/$key/b2/run.json' \
      --base-url '$base' --model-id '$model'" \
    "$b2"

  run_one "$key V" \
    "'$PYBIN' -m validator.validator_v \
      --config configs/validator_v/development.yaml \
      --gather --live --limit 30 --claim-ids-file '$SAMPLE' \
      --workers $workers \
      --output '$v' --run-sidecar '$OUT/$key/v/run.json' \
      --base-url '$base' --model-id '$model'" \
    "$v"

  if [ "$kind" = "closed" ]; then
    echo "== $key closed; cumulative spend \$$(spend_so_far)"
  fi
done

echo "== sweep finished; cumulative closed-model spend \$$(spend_so_far)"
