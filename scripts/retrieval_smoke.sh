#!/usr/bin/env bash
# Turing-Machine smoke: BM25 index twice (byte-identical) and gather-dev10.
# Does not wire retrieval into the judge. Run from anywhere; paths are repo-rooted.
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
export PYTHONPATH="${root}/src${PYTHONPATH:+:$PYTHONPATH}"

config="configs/retrieval/scifact_bm25.yaml"
index="artifacts/retrieval/scifact_bm25.json"
first="artifacts/retrieval/scifact_bm25.first.json"
bundles="artifacts/retrieval/dev10_bundles.jsonl"

python3 -m data.pins.scifact.download_verify

python3 -m validator.retrieve index --config "$config"
cp "$index" "$first"
python3 -m validator.retrieve index --config "$config"
cmp "$index" "$first"
rm "$first"

python3 -m validator.retrieve gather-dev10 --config "$config" --output "$bundles"

python3 -c '
import json
from pathlib import Path
expected = [
    "scifact:0", "scifact:2", "scifact:4", "scifact:6", "scifact:9",
    "scifact:10", "scifact:11", "scifact:12", "scifact:14", "scifact:15",
]
path = Path("artifacts/retrieval/dev10_bundles.jsonl")
ids = [json.loads(line)["claim_id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
if ids != expected:
    raise SystemExit("claim ids " + repr(ids))
print("bundles=%d" % len(ids))
'

echo OK
