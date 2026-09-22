# Retrieval BM25 smoke

Retrieval BM25 smoke builds the SciFact BM25 index twice (byte-identical), gathers the fixed ten development claim bundles, and prints `OK` without wiring retrieval into the judge.

## Sub-features

- `retrieval-index` builds `artifacts/retrieval/scifact_bm25.json` from `configs/retrieval/scifact_bm25.yaml`.
- `retrieval-idempotent` rebuilds and `cmp`s the index for byte identity.
- `retrieval-gather-dev10` writes `artifacts/retrieval/dev10_bundles.jsonl` with the locked ten claim ids.

## How to get to it (user POV)

- From the repository root after bootstrap, run `bash scripts/retrieval_smoke.sh`.
- Manual steps: `PYTHONPATH=src python3 -m validator.retrieve index` then `gather-dev10` (see `docs/retrieval/TURING_MACHINE_SMOKE.md`).

## Driving it with the shell

Preconditions:

- Doctor `retrieval_ready=yes` (SciFact raw present and pin-matched).
- Enough disk for the index under `artifacts/retrieval/`.

- **Run smoke.** Execute `bash scripts/retrieval_smoke.sh`. Exit code `0`. Final stdout line is `OK`.
- **Confirm bundles.** Check `artifacts/retrieval/dev10_bundles.jsonl` exists with claim ids `scifact:0`, `scifact:2`, `scifact:4`, `scifact:6`, `scifact:9`, `scifact:10`, `scifact:11`, `scifact:12`, `scifact:14`, `scifact:15` in that order.
- **Proof.** Copy or tee the smoke transcript to `artifacts/verify-mavs/retrieval/transcript.txt` (create the directory). Leave the index/bundles under `artifacts/retrieval/` as the side-effect proof.

## Gotchas

- Skip this feature when SciFact is not bootstrapped; report `retrieval_ready=no`.
- The smoke path does not call the judgment stack or LM Studio.
- Index outputs are gitignored; do not delete them during cleanup if they are this run's evidence.
