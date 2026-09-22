# SciFact corpus lock

Pinned AllenAI SciFact release for the corpus-lock slice. Raw JSONL files are downloaded into `data/raw/scifact/` and are not committed. Public SciFact development claims are the project held-out local eval (`held_out_local_eval`). That split is not a community test. Official test claims stay unlabeled. Empty evidence is not a four-way label.

## Commands

Turing-Machine path: clone the repo and run from the repository root (the directory that contains `data/`). There is no machine-specific absolute path. Dependencies: `pydantic`, `jsonschema`, and `pyyaml`. The one command below is the bootstrap. It runs download_verify, then the smoke check, and exits non-zero on any mismatch. It does not rewrite `LOCKED.json`. Details: [BOOTSTRAP.md](BOOTSTRAP.md).

```bash
python3 -m data.bootstrap_scifact
```

The same two steps, if you run them separately:

```bash
python3 -m data.pins.scifact.download_verify
python3 -m data.smoke_scifact_splits
```

`python -m data.smoke_scifact_splits` is the same module when `python` is Python 3. This environment has `python3` on `PATH`.

The smoke command downloads and verifies when the raw files are missing or do not match the pin. It prints the locked row counts, recomputes every manifest `ids_sha256`, and schema-validates one claim and evidence sample from development, calibration, and held_out_local_eval, plus one official-test claim without requiring labels. Expected counts on `SMOKE OK`: calibration 100, development 709, held_out_local_eval 300, official_test_unlabeled 300, corpus 5183. A hash or count mismatch fails the process. Do not regenerate splits or rewrite `LOCKED.json` to make it pass.

## Upstream

| Name | Value |
| --- | --- |
| Upstream repo commit | `68b98a56d93e0f9da0d2aab4e6c3294699a0f72e` (`allenai/scifact`) |
| Data URL | `https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz` |
| `tarball_sha256` | `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be` |
| Calibration salt | `mavs-scifact-calibration-v1` |

## Paths

| Path | Role |
| --- | --- |
| `data/pins/scifact/PIN.json` | Source URL, commit, tarball hash, file hashes, split policy (`locked=true`) |
| `data/pins/scifact/LOCKED.json` | Lock record (`locked=true`) and manifest `ids_sha256` values |
| `data/pins/scifact/download_verify.py` | Download, sha256 check, extract into `data/raw/scifact/` |
| `data/bootstrap_scifact.py` | One-command bootstrap: download_verify, then smoke |
| `data/pins/scifact/BOOTSTRAP.md` | Turing-Machine bootstrap note |
| `data/pins/scifact/README.md` | This note |
| `configs/corpus/scifact.yaml` | Points at the pin, lock, manifests, raw dir, and `corpus_hash` |
| `data/scifact_loader.py` | Claim plus same-evidence / gold bundle loader |
| `data/smoke_scifact_splits.py` | One-command smoke check |
| `src/validator/schemas.py` | Run, Claim, Evidence, Judgment, ReportVerdict models |
| `schemas/` | JSON schemas copied for those records and the native SciFact files |

`corpus_hash` in `configs/corpus/scifact.yaml` is the `corpus.jsonl` sha256 below. `doc_id` is the SciFact S2ORC integer. `snapshot_hash` is the SHA-256 of canonical corpus-document JSON: UTF-8, sorted keys, compact separators, fields `abstract`, `doc_id`, `structured`, `title`. `ids_sha256` is the SHA-256 of the decimal claim ids, one per line, with a trailing newline.

## Raw files (gitignored under `/data/raw/`)

| Path | SHA-256 | Records |
| --- | --- | --- |
| `data/raw/scifact/claims_train.jsonl` | `f4c8fa82d8bd0653a9cc8d61a6ea48c25eacea64e90af5dbf390ebb1b74372f0` | 809 |
| `data/raw/scifact/claims_dev.jsonl` | `86f0435d08fdb65d1aa41d1472684f57e6e71930626497bdf4d7a9ec1a632217` | 300 |
| `data/raw/scifact/claims_test.jsonl` | `558930d75215c73f84a28fe538307d6d397c9de1ec7239514cf45f80d75d2ca3` | 300 |
| `data/raw/scifact/corpus.jsonl` | `b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62` | 5183 |

## Locked manifests

| Path | Role | `ids_sha256` | Ids |
| --- | --- | --- | --- |
| `manifests/scifact/scifact_train_all.json` | `source_train` | `ad7e39aa19e1b37cbcf11820b9ff3dfe5d674578c4fba92e3db220816d0b2a04` | 809 |
| `manifests/scifact/scifact_calibration_v1.json` | `calibration` | `6221cf17180dcad32e2655503d2138621701b8f3dfe32bd6afff4bcd9820b311` | 100 |
| `manifests/scifact/scifact_development_v1.json` | `development` | `d1a5b5a09e7a61b3216b1d816d4cf1ea85426dfa721d8f0561ba5dd3bd30c2dd` | 709 |
| `manifests/scifact/scifact_held_out_dev_v1.json` | `held_out_local_eval` | `f454ba3f4706f9623699bdf722a170c1b97f28b74c325c927d428a2d81279b92` | 300 |
| `manifests/scifact/scifact_official_test_v1.json` | `official_test_unlabeled` | `b08b7a25df70a05fe97c7bbbdad2e218985431d1508159b9c9033867d9d991df` | 300 |

## JSON schemas

| Path |
| --- |
| `schemas/scifact_claim_native.schema.json` |
| `schemas/scifact_corpus_doc.schema.json` |
| `schemas/mavs_claim_record.schema.json` |
| `schemas/mavs_evidence_record.schema.json` |
| `schemas/mavs_evidence_label.schema.json` |
| `schemas/mavs_label_record.schema.json` |
| `schemas/mavs_run_record.schema.json` |
| `schemas/mavs_report_verdict.schema.json` |
