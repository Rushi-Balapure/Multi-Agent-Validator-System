# Turing-Machine BM25 index and gather-dev10 smoke

Local clone on `main`. SciFact raw files are not in git. Download them first, then build the pure-Python BM25 index twice and gather the 10 pinned development claims. This note does not add a retrieval protocol. Product wiring of gather output into the Judge Stack is out of this MR.

Pinned `corpus.jsonl` sha256 (`corpus_hash`):

`b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62`

Fixed development claim ids (first 10 ids in `manifests/scifact/scifact_development_v1.json`, project form `scifact:{native_id}`):

`scifact:0`, `scifact:2`, `scifact:4`, `scifact:6`, `scifact:9`, `scifact:10`, `scifact:11`, `scifact:12`, `scifact:14`, `scifact:15`

Config: `configs/retrieval/scifact_bm25.yaml`. Index and bundles are gitignored under `artifacts/retrieval/`.

From the repository root, with `pydantic`, `jsonschema`, and `pyyaml` installed (`python3 -m pip install -e ".[dev]"`):

```bash
python3 -m data.pins.scifact.download_verify

PYTHONPATH=src python3 -m validator.retrieve index \
  --config configs/retrieval/scifact_bm25.yaml

cp artifacts/retrieval/scifact_bm25.json artifacts/retrieval/scifact_bm25.first.json

PYTHONPATH=src python3 -m validator.retrieve index \
  --config configs/retrieval/scifact_bm25.yaml

cmp artifacts/retrieval/scifact_bm25.json artifacts/retrieval/scifact_bm25.first.json
rm artifacts/retrieval/scifact_bm25.first.json

PYTHONPATH=src python3 -m validator.retrieve gather-dev10 \
  --config configs/retrieval/scifact_bm25.yaml \
  --output artifacts/retrieval/dev10_bundles.jsonl
```

`index` refuses to write unless `data/raw/scifact/corpus.jsonl` matches `corpus_hash` and `configs/corpus/scifact.yaml`. The index file is canonical JSON (`sort_keys`, compact separators, trailing newline) with no timestamp. A second build of the same corpus and config replaces `artifacts/retrieval/scifact_bm25.json` with the same bytes. `cmp` exits 0 and prints nothing when the two files are byte-identical. The file mtime changes; the bytes do not.

`gather-dev10` writes one JSON object per line, in the pinned id order. Confirm the ids:

```bash
PYTHONPATH=src python3 -c '
import json
from pathlib import Path
expected = [
    "scifact:0", "scifact:2", "scifact:4", "scifact:6", "scifact:9",
    "scifact:10", "scifact:11", "scifact:12", "scifact:14", "scifact:15",
]
path = Path("artifacts/retrieval/dev10_bundles.jsonl")
ids = [json.loads(line)["claim_id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
if ids != expected:
    raise SystemExit(f"claim ids {ids}")
print(f"bundles={len(ids)}")
'
```

`scripts/retrieval_smoke.sh` runs the download, both index builds, `cmp`, and `gather-dev10`. It prints `OK` after the index files match and the ten claim ids match.

## Phase-2 independent gatherer (prep only)

Product wiring is out of this MR. These bullets are notes for the next retrieval slice. They do not change the gather protocol on `main`.

Already on `main`:

- Pure-Python Okapi BM25 (`k1=1.5`, `b=0.75`, epsilon idf floor) and `python3 -m validator.retrieve index`.
- `gather` and `gather-dev10` for the ten fixed development claim ids.
- Query variants: `open_inquiry`, `scope_measurement`, and `limitations_null` (`{text}` plus the scope and limitations templates in `configs/retrieval/scifact_bm25.yaml`).
- Per query, the top 20 positive BM25 hits; union deduped by document id and normalized abstract; rerank `max_bm25`; at most 8 passages.
- `EvidenceBundle` records (`retrieval_round` 1, `corpus_hash`, D1 passages). The Judge Stack can accept an `EvidenceBundle` when a fixture passes one in (`judge_claim`, `validator.fixture_pipeline`). That path does not call `gather` and does not build this index.

Still for a later Phase-2 gatherer slice:

- Dense retrieval.
- Reciprocal-rank fusion: sum `1 / (60 + rank)` across lists. The current rerank is max BM25 only.
- Wiring live `gather` / `gather-dev10` bundles into Judge Stack `EvidenceBundle` consumption. Fixture bundles are not this index.
- Round-2 retrieval. The research plan runs a second round only for unresolved questions, scope mismatch, or contradictory evidence. `RetrievalConfig.retrieval_round` is locked to 1.
