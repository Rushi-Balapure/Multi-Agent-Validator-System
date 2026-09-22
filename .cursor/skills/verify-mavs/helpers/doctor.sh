#!/usr/bin/env bash
# Read-only health check for Multi-Agent-Validator-System CLI verification.
# Exit 0 when the offline surface is ready. Prints whether LM Studio :1234 is up.
set -euo pipefail

root="$(cd "$(dirname "$0")/../../../.." && pwd)"
cd "$root"
export PYTHONPATH="${root}/src${PYTHONPATH:+:$PYTHONPATH}"

echo "repo_root=$root"
echo "python=$(python3 -c 'import sys; print(sys.version.split()[0])')"

python3 - <<'PY'
import importlib
import sys

missing = []
for name in ("pydantic", "yaml", "jsonschema"):
    try:
        importlib.import_module(name)
    except ImportError:
        missing.append(name)
if missing:
    print("deps=MISSING " + ",".join(missing))
    sys.exit(1)
print("deps=ok")

try:
    importlib.import_module("validator.same_evidence.runner")
    importlib.import_module("evaluation.score_predictions")
    importlib.import_module("validator.fixture_pipeline")
    importlib.import_module("validator.retrieve")
except Exception as exc:  # noqa: BLE001 — doctor surfaces any import failure
    print(f"imports=FAIL {exc}")
    sys.exit(1)
print("imports=ok PYTHONPATH=src")
PY

pin="data/pins/scifact/PIN.json"
locked="data/pins/scifact/LOCKED.json"
if [[ ! -f "$pin" || ! -f "$locked" ]]; then
  echo "corpus_pin=MISSING"
  exit 1
fi
echo "corpus_pin=present $pin"

raw_ok=0
if [[ -f data/raw/scifact/corpus.jsonl ]]; then
  if python3 -m data.pins.scifact.download_verify >/tmp/mavs-doctor-download_verify.log 2>&1; then
    echo "corpus_raw=ok (hashes match PIN.json)"
    raw_ok=1
  else
    echo "corpus_raw=MISMATCH (see /tmp/mavs-doctor-download_verify.log)"
    exit 1
  fi
else
  echo "corpus_raw=absent (run: python3 -m data.bootstrap_scifact)"
fi

lmstudio="down"
if command -v curl >/dev/null 2>&1; then
  code="$(curl -s -o /dev/null -w '%{http_code}' --connect-timeout 1 http://127.0.0.1:1234/v1/models || true)"
  if [[ "$code" == "200" ]]; then
    lmstudio="up"
  fi
fi
echo "lmstudio_1234=$lmstudio"

echo "offline_ready=yes"
if [[ "$raw_ok" -eq 1 ]]; then
  echo "retrieval_ready=yes"
else
  echo "retrieval_ready=no (bootstrap SciFact first)"
fi
if [[ "$lmstudio" == "up" ]]; then
  echo "live_ready=yes"
else
  echo "live_ready=no (optional; dry-run and offline fixture paths still work)"
fi
