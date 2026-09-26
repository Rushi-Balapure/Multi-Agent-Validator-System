#!/usr/bin/env bash
# Phase-1 reproducibility smoke: dry-run same-evidence B2, then score a fixture.
# Offline. No GPU, no LM Studio, no download. Exits 0 on success.
# From the repo root: bash scripts/phase1_smoke.sh
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
export PYTHONPATH="${root}/src${PYTHONPATH:+:$PYTHONPATH}"
# Honour the caller's interpreter so a virtualenv that holds the dependencies
# can run this script without them also being installed for bare python3.
PYBIN="${MAVS_PYTHON:-python3}"

out="${PHASE1_SMOKE_OUT:-artifacts/phase1_smoke}"
mkdir -p "$out"
predictions="${out}/predictions.jsonl"
sidecar="${out}/run.json"
metrics="${out}/metrics.json"

"$PYBIN" - "$root" "$predictions" "$sidecar" <<'PY'
import json
import socket
import sys
import urllib.request
from pathlib import Path

root = Path(sys.argv[1])
predictions_path = Path(sys.argv[2])
sidecar_path = Path(sys.argv[3])


def _refuse_network(*_args, **_kwargs):
    raise RuntimeError("phase-1 smoke refused a network call")


socket.create_connection = _refuse_network  # type: ignore[method-assign]
urllib.request.urlopen = _refuse_network  # type: ignore[method-assign]

from validator.same_evidence.b2 import MockClient, run_b2
from validator.same_evidence.inputs import PredictInput

example_path = root / "tests" / "fixtures" / "phase1" / "example_claim.json"
raw = json.loads(example_path.read_text(encoding="utf-8"))
license_text = raw.pop("license", "")
if "MIT" not in license_text or "Synthetic" not in license_text:
    raise SystemExit("phase1 smoke: example_claim.json must stay a MIT synthetic example")
item = PredictInput.model_validate(raw)
prompts = root / "prompts" / "same_evidence"
# Same client --dry-run selects in validator.same_evidence.runner (MockClient).
row = run_b2(
    item,
    seed=0,
    neutral_template=(prompts / "b2_neutral_question_v1.txt").read_text(encoding="utf-8"),
    reader_prompt=(prompts / "b2_reader_v1.txt").read_text(encoding="utf-8"),
    compare_prompt=(prompts / "b2_compare_v1.txt").read_text(encoding="utf-8"),
    client=MockClient(0),
)
if row.get("inference_mode") != "mock":
    raise SystemExit(f"phase1 smoke: expected inference_mode=mock, got {row.get('inference_mode')!r}")
if row.get("label") not in {"SUPPORT", "REFUTE", "NEI"}:
    raise SystemExit(f"phase1 smoke: dry-run label {row.get('label')!r} is outside SUPPORT/REFUTE/NEI")
blob = json.dumps(row)
if "asserted_answer" in blob or "rationales" in blob:
    raise SystemExit("phase1 smoke: dry-run prediction leaked gold fields")
predictions_path.parent.mkdir(parents=True, exist_ok=True)
predictions_path.write_text(
    json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
    encoding="utf-8",
)
sidecar = {
    "system_id": "same_evidence_baseline",
    "adaptation": "B2",
    "inference_mode": "mock",
    "model_invoked": False,
    "dry_run": True,
    "input_source": "phase1_synthetic_example",
    "example": "tests/fixtures/phase1/example_claim.json",
    "n_predictions": 1,
    "note": "MIT synthetic example. Not the locked SciFact corpus. MockClient is the --dry-run client.",
    "run": {"run_id": "phase1-smoke-synthetic-dry-run"},
}
sidecar_path.write_text(json.dumps(sidecar, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"dry-run mock wrote {predictions_path} inference_mode=mock label={row['label']}")
PY

# Official CLI when the pinned corpus is already on disk. Never downloads.
if "$PYBIN" -c 'from data.pins.scifact.download_verify import raw_matches_pin, repo_root; raise SystemExit(0 if raw_matches_pin(repo_root()) else 1)'; then
  "$PYBIN" -m validator.same_evidence.runner \
    --config configs/baseline/same_evidence_b2.yaml \
    --dry-run --limit 1 \
    --output "${out}/corpus_dry_run_predictions.jsonl" \
    --run-sidecar "${out}/corpus_dry_run_run.json"
else
  echo "pinned SciFact raw files absent; skipped validator.same_evidence.runner --dry-run (no download)"
fi

"$PYBIN" -m evaluation.score_predictions \
  --predictions src/evaluation/fixtures/b2_predictions.jsonl \
  --run-id fixture-b2-score-001 \
  --output "$metrics"

"$PYBIN" - "$metrics" "$root/src/evaluation/fixtures/b2_metrics_expected.json" "$predictions" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
expected = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
for key, value in expected.items():
    if report.get(key) != value:
        raise SystemExit(f"phase1 smoke: metrics mismatch on {key}")
if report.get("n_scored", 0) < 1:
    raise SystemExit("phase1 smoke: scorer wrote no scored rows")
rows = [
    json.loads(line)
    for line in Path(sys.argv[3]).read_text(encoding="utf-8").splitlines()
    if line.strip()
]
if len(rows) != 1 or rows[0].get("inference_mode") != "mock":
    raise SystemExit("phase1 smoke: predictions.jsonl is not the one-row mock dry-run")
print(
    f"scored {report['n_scored']} fixture rows run_id={report['run_id']} "
    f"-> {sys.argv[1]}"
)
PY

echo "phase1 smoke OK"
