#!/usr/bin/env bash
# Phase-3 Stack V gather smoke for Turing-Machine.
#
# Offline CI stays on scripts/validator_v_smoke.sh (--dry-run fixtures).
# This script documents the live/gather path against Retrieval Wing BM25 and
# LM Studio at http://127.0.0.1:1234/v1. It does not invent scores when the
# SciFact index or LM Studio is missing; it exits non-zero with the command.
#
# D0 on --gather: SciFact native cited_doc_ids abstracts (provenance=original),
# joined from corpus.jsonl. Gold evidence SUPPORT/CONTRADICT rationales are not
# loaded as D0. Retrieval gather stays D1-only (neutral question + claim_id).
#
# Claim ids match B2 live run same-evidence-b2-development-s0-n20-dac855c4e2ae
# (first 20 locked development ids, that order).
#
# From the repo root on Turing-Machine:
#   bash scripts/validator_v_phase3_gather_smoke.sh
# Optional:
#   VALIDATOR_V_PHASE3_OUT=artifacts/validator_v_phase3 bash scripts/validator_v_phase3_gather_smoke.sh
#   VALIDATOR_V_PHASE3_LIVE=0  # gather only (mock judge); still needs BM25 index + corpus
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
export PYTHONPATH="${root}/src${PYTHONPATH:+:$PYTHONPATH}"

CLAIM_IDS="scifact:0,scifact:2,scifact:4,scifact:6,scifact:9,scifact:10,scifact:11,scifact:12,scifact:14,scifact:15,scifact:17,scifact:18,scifact:19,scifact:20,scifact:21,scifact:22,scifact:24,scifact:25,scifact:26,scifact:27"

out="${VALIDATOR_V_PHASE3_OUT:-artifacts/validator_v}"
mkdir -p "$out"
predictions="${out}/predictions.jsonl"
sidecar="${out}/run.json"
retrieval_smoke="${out}/dev20_phase3_smoke.jsonl"

live_flag=(--live)
if [[ "${VALIDATOR_V_PHASE3_LIVE:-1}" == "0" ]]; then
  live_flag=()
fi

echo "Phase-3 claim ids (B2 order): ${CLAIM_IDS}"

# Retrieval Wing gather smoke (index + claims_jsonl required).
if ! PYTHONPATH=src python3 -m validator.retrieve gather-claims \
  --config configs/retrieval/scifact_bm25.yaml \
  --claim-ids "${CLAIM_IDS}" \
  --output "${retrieval_smoke}"; then
  cat <<EOF >&2
validator_v_phase3_gather_smoke: Retrieval Wing gather-claims failed.
On Turing-Machine: build the BM25 index, then re-run. Exact command:

  PYTHONPATH=src python3 -m validator.retrieve gather-claims \\
    --config configs/retrieval/scifact_bm25.yaml \\
    --claim-ids ${CLAIM_IDS} \\
    --output artifacts/retrieval/dev20_phase3_smoke.jsonl

This Cloud VM does not invent live retrieval scores.
EOF
  exit 2
fi

# Stack V staged gather over the same ids. --live needs LM Studio :1234.
if ! PYTHONPATH=src python3 -m validator.validator_v \
  --config configs/validator_v/development.yaml \
  --gather \
  "${live_flag[@]}" \
  --claim-ids "${CLAIM_IDS}" \
  --limit 20 \
  --output "${predictions}" \
  --run-sidecar "${sidecar}"; then
  cat <<EOF >&2
validator_v_phase3_gather_smoke: Stack V --gather failed.
When the SciFact index and LM Studio (http://127.0.0.1:1234/v1) are up:

  PYTHONPATH=src python3 -m validator.validator_v \\
    --config configs/validator_v/development.yaml \\
    --gather --live --limit 20 \\
    --claim-ids ${CLAIM_IDS} \\
    --output artifacts/validator_v/predictions.jsonl \\
    --run-sidecar artifacts/validator_v/run.json

Offline CI: bash scripts/validator_v_smoke.sh
EOF
  exit 2
fi

python3 - "$predictions" "$sidecar" <<'PY'
import json
import sys
from pathlib import Path

PHASE3 = [
    "scifact:0", "scifact:2", "scifact:4", "scifact:6", "scifact:9",
    "scifact:10", "scifact:11", "scifact:12", "scifact:14", "scifact:15",
    "scifact:17", "scifact:18", "scifact:19", "scifact:20", "scifact:21",
    "scifact:22", "scifact:24", "scifact:25", "scifact:26", "scifact:27",
]
predictions = Path(sys.argv[1])
sidecar_path = Path(sys.argv[2])
rows = [json.loads(line) for line in predictions.read_text(encoding="utf-8").splitlines() if line.strip()]
if [row["claim_id"] for row in rows] != PHASE3:
    raise SystemExit(f"phase3 gather smoke: claim_id order drifted: {[r['claim_id'] for r in rows]}")
labels = {"SUPPORT", "REFUTE", "NEI"}
for row in rows:
    if row.get("method_id") != "V":
        raise SystemExit(f"phase3 gather smoke: method_id {row.get('method_id')!r}")
    if row.get("label") not in labels:
        raise SystemExit(f"phase3 gather smoke: label {row.get('label')!r}")
sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
if sidecar.get("method_id") != "V" or sidecar.get("input_source") != "gather":
    raise SystemExit("phase3 gather smoke: sidecar method_id or input_source")
run = sidecar.get("run") or {}
run_id = run.get("run_id") or ""
if not run_id.startswith("validator-v-gather-"):
    raise SystemExit(f"phase3 gather smoke: unexpected run_id {run_id!r}")
if "n3-" in run_id:
    raise SystemExit(f"phase3 gather smoke: refused fixture n3 run_id {run_id!r}")
print(f"validator v phase3 gather smoke OK n={len(rows)} run_id={run_id} inference_mode={sidecar.get('inference_mode')}")
PY
