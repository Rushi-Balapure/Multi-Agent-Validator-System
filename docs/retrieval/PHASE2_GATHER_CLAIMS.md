# Phase-2 MR1: gather-claims

Round-1 product path. `gather(claim_or_neutral_question, config, claim_id)` already accepted any project `claim_id`. This MR wires a CLI that does too. It does not change the query protocol and it does not run dense retrieval, reciprocal-rank fusion, or a second round.

`gather-claims` loads **claim text only** through `load_claim_texts`. Gold labels, citations, and asserted answers are not gather inputs.

Default selection is the first 5 ids in the locked development manifest (`manifests/scifact/scifact_development_v1.json`): `scifact:0`, `scifact:2`, `scifact:4`, `scifact:6`, `scifact:9`.

```bash
PYTHONPATH=src python3 -m validator.retrieve gather-claims \
  --config configs/retrieval/scifact_bm25.yaml \
  --limit 5 \
  --output artifacts/retrieval/dev5_bundles.jsonl

PYTHONPATH=src python3 -m validator.retrieve gather-claims \
  --config configs/retrieval/scifact_bm25.yaml \
  --claim-ids scifact:0,scifact:2,scifact:4,scifact:6,scifact:9 \
  --output artifacts/retrieval/dev5_bundles.jsonl
```

Use `--claim-ids` or `--manifest` with `--limit`, not both. `--limit` defaults to 5 only when `--claim-ids` is omitted. Each bundle is one JSON object per line. The log line per bundle is `format_bundle_log` (query text, hit ids, ranks, reranked ids).

`gather-dev10` is unchanged in behavior: it still checks `fixed_claim_ids` against the first 10 development ids, then calls the same writer.

Protocol, unchanged: three forms (`open_inquiry`, `scope_measurement`, `limitations_null`), top 20 positive BM25 hits per form, dedupe, rerank `max_bm25`, at most 8 passages, `retrieval_round` 1.

## Round 2 and RRF (locked off)

`configs/retrieval/scifact_bm25.yaml` records prep flags. They are not a product path.

- `round2.enabled` is false. A later round would start only for an unresolved question, scope mismatch, or contradictory evidence, and would stop on exhausted budget, no new eligible documents, or a complete bounded evidence record. `retrieval_round` stays 1, so gather does not take that branch.
- `rrf.enabled` is false and `rrf.k` is 60. Fusion would be `1 / (60 + rank)` summed across lists. `rerank` stays `max_bm25`.
- Dense retrieval is not configured.

## Checks

```bash
PYTHONPATH=src python3 -m validator.retrieve gather-claims \
  --config configs/retrieval/scifact_bm25.yaml \
  --limit 5 \
  --output artifacts/retrieval/dev5_bundles.jsonl
bash scripts/retrieval_smoke.sh
pytest tests/test_retrieve.py -q
```

`scripts/retrieval_smoke.sh` is still the index idempotence check plus `gather-dev10`.
