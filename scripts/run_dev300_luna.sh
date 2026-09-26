#!/usr/bin/env bash
# Live gpt-6-luna run on the frozen development 300. Does not touch held-out.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYBIN="${MAVS_PYTHON:-python3}"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
SAMPLE="data/manifests/dev300_seed42.json"

echo "B2 live n=300"
"$PYBIN" -m validator.same_evidence.runner \
  --config configs/baseline/same_evidence_b2.yaml \
  --live --limit 300 \
  --claim-ids-file "$SAMPLE" \
  --workers 8 \
  --output artifacts/same_evidence_b2_dev300/predictions.jsonl \
  --run-sidecar artifacts/same_evidence_b2_dev300/run.json

echo "V gather live n=300"
"$PYBIN" -m validator.validator_v \
  --config configs/validator_v/development.yaml \
  --gather --live --limit 300 \
  --claim-ids-file "$SAMPLE" \
  --workers 4 \
  --output artifacts/validator_v_dev300/predictions.jsonl \
  --run-sidecar artifacts/validator_v_dev300/run.json

echo "score + bootstrap"
"$PYBIN" -m evaluation.compare_runs \
  --b2-predictions artifacts/same_evidence_b2_dev300/predictions.jsonl \
  --v-predictions artifacts/validator_v_dev300/predictions.jsonl \
  --b2-sidecar artifacts/same_evidence_b2_dev300/run.json \
  --v-sidecar artifacts/validator_v_dev300/run.json \
  --join-gold development \
  --output docs/paper-assets/tables/dev300_b2_vs_v.json

"$PYBIN" scripts/paper/make_tables.py
echo "dev300 complete"
