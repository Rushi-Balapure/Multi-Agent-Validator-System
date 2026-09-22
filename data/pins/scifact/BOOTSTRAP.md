# SciFact bootstrap (Turing-Machine)

One-command download and lock check for a fresh clone. This is the Turing-Machine path.

Clone the repository and run from the repository root: the directory that contains `data/`, `configs/`, `manifests/`, and `schemas/`. The path is that clone root. There is no machine-specific absolute path.

## Dependencies

Python 3.11 or newer, with:

- `pydantic`
- `jsonschema`
- `pyyaml`

From the repository root:

```bash
python3 -m pip install pydantic jsonschema pyyaml
```

`python3 -m pip install -e .` installs the same three packages from `pyproject.toml`.

## Command

```bash
python3 -m data.bootstrap_scifact
```

That runs, in order, and stops on the first non-zero exit:

```bash
python3 -m data.pins.scifact.download_verify
python3 -m data.smoke_scifact_splits
```

`download_verify` fetches the pinned tarball when `data/raw/scifact/` is missing or does not match `PIN.json`, checks `tarball_sha256`, and extracts the four JSONL files. Raw files stay gitignored. `smoke_scifact_splits` checks those files again (it calls `ensure_scifact_raw`), recomputes every manifest `ids_sha256`, and schema-validates one sample from development, calibration, and held_out_local_eval, plus one official-test claim without labels.

A successful run prints `SMOKE OK` and then `BOOTSTRAP OK`.

## Expected SMOKE OK counts

| Split | Count |
| --- | --- |
| calibration | 100 |
| development | 709 |
| held_out_local_eval | 300 |
| official_test_unlabeled | 300 |
| corpus | 5183 |

## Locked hashes

These values are already locked. Do not edit them here. The same hashes are in `README.md`, `LOCKED.json`, and `PIN.json`.

| Name | SHA-256 |
| --- | --- |
| `tarball_sha256` | `11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be` |
| `claims_train.jsonl` | `f4c8fa82d8bd0653a9cc8d61a6ea48c25eacea64e90af5dbf390ebb1b74372f0` |
| `claims_dev.jsonl` | `86f0435d08fdb65d1aa41d1472684f57e6e71930626497bdf4d7a9ec1a632217` |
| `claims_test.jsonl` | `558930d75215c73f84a28fe538307d6d397c9de1ec7239514cf45f80d75d2ca3` |
| `corpus.jsonl` | `b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62` |

| Manifest | `ids_sha256` |
| --- | --- |
| `scifact_train_all` | `ad7e39aa19e1b37cbcf11820b9ff3dfe5d674578c4fba92e3db220816d0b2a04` |
| `scifact_calibration_v1` | `6221cf17180dcad32e2655503d2138621701b8f3dfe32bd6afff4bcd9820b311` |
| `scifact_development_v1` | `d1a5b5a09e7a61b3216b1d816d4cf1ea85426dfa721d8f0561ba5dd3bd30c2dd` |
| `scifact_held_out_dev_v1` | `f454ba3f4706f9623699bdf722a170c1b97f28b74c325c927d428a2d81279b92` |
| `scifact_official_test_v1` | `b08b7a25df70a05fe97c7bbbdad2e218985431d1508159b9c9033867d9d991df` |

Upstream repo commit: `68b98a56d93e0f9da0d2aab4e6c3294699a0f72e`. Calibration salt: `mavs-scifact-calibration-v1`.

## Refuse silent regeneration

If a hash or count does not match `LOCKED.json` or `PIN.json`, `python3 -m data.bootstrap_scifact` exits non-zero. It does not rewrite `LOCKED.json`, `PIN.json`, manifests, or schemas, and it does not regenerate splits. Report the mismatch. A new lock requires a new versioned lock file and a separate change.
