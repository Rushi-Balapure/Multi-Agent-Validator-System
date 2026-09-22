# Bootstrap SciFact

Bootstrap SciFact downloads the pinned SciFact tarball when needed, checks file hashes against `PIN.json`, validates split manifests, and prints `BOOTSTRAP OK` so later CLI drives can load the locked corpus.

## Sub-features

- `bootstrap-download` fetches and extracts the pinned tarball into `data/raw/scifact/` when missing or mismatched.
- `bootstrap-smoke` recomputes manifest `ids_sha256` values and schema-validates sample claims.
- `bootstrap-refuse` exits non-zero on hash or count mismatch without rewriting lock files.

## How to get to it (user POV)

- From the repository root, run `python3 -m data.bootstrap_scifact`.
- Equivalent first half alone: `python3 -m data.pins.scifact.download_verify`.

## Driving it with the shell

Preconditions:

- Repository root, Python deps installed (`pydantic`, `jsonschema`, `PyYAML`).
- Network available for the first download when `data/raw/scifact/` is absent.
- Doctor reports `corpus_pin=present`.

- **Run bootstrap.** Execute `python3 -m data.bootstrap_scifact`. Exit code `0`. Stdout contains `SMOKE OK` then `BOOTSTRAP OK`.
- **Confirm raw files.** Check that `data/raw/scifact/corpus.jsonl` and the three claims JSONL files exist.
- **Re-run verify.** Execute `python3 -m data.pins.scifact.download_verify`. Exit code `0` with hashes matching `data/pins/scifact/PIN.json`.
- **Proof.** Save the bootstrap transcript to `artifacts/verify-mavs/bootstrap/transcript.txt` (create the directory first). Include the final `BOOTSTRAP OK` line and exit code.

## Gotchas

- A hash mismatch must fail the run. Do not edit `PIN.json`, `LOCKED.json`, or manifests to force green.
- `data/raw/` is gitignored; absence after a fresh clone is expected until bootstrap runs.
- Offline air-gapped hosts without an existing raw tree cannot complete download; report the network precondition.
