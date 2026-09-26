"""Write docs/freeze.json from completed live sidecars plus the corpus pin."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SIDECARS = {
    "B2": ROOT / "artifacts" / "same_evidence_b2_dev300" / "run.json",
    "V": ROOT / "artifacts" / "validator_v_dev300" / "run.json",
    "B0": ROOT / "artifacts" / "baselines" / "b0" / "run.json",
    "B1": ROOT / "artifacts" / "baselines" / "b1" / "run.json",
    "O": ROOT / "artifacts" / "baselines" / "oracle" / "run.json",
    "B3": ROOT / "artifacts" / "baselines" / "b3" / "run.json",
}


def git_commit() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return proc.stdout.strip()


def sidecar_run(path: Path) -> dict | None:
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    run = payload.get("run") if isinstance(payload, dict) else None
    return run if isinstance(run, dict) else None


def main() -> int:
    pin = json.loads((ROOT / "data" / "pins" / "scifact" / "PIN.json").read_text(encoding="utf-8"))
    corpus_hash = pin["files"]["corpus.jsonl"]["sha256"]
    methods: dict[str, dict] = {}
    model_id = "gpt-6-luna"
    for name, path in SIDECARS.items():
        run = sidecar_run(path)
        if run is None:
            continue
        methods[name] = {
            "run_id": run.get("run_id"),
            "model_id": run.get("model_id"),
            "config_hash": run.get("config_hash"),
            "prompt_hash": run.get("prompt_hash"),
            "corpus_hash": run.get("corpus_hash"),
        }
        if run.get("model_id"):
            model_id = run["model_id"]
    record = {
        "freeze_id": "held-out-v1",
        "model_id": model_id,
        "primary_metric": "false_endorsement_gold_nonsup",
        "primary_comparison": "V versus B2",
        "sample": "data/manifests/dev300_seed42.json",
        "held_out_split": "held_out_local_eval",
        "corpus_hash": corpus_hash,
        "code_commit": git_commit(),
        "methods": methods,
        "note": (
            "Held-out 300 may run only with --frozen-final. "
            "model_id and corpus_hash must match. Per-method prompt/config "
            "hashes are checked when that method is present."
        ),
    }
    path = ROOT / "docs" / "freeze.json"
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path} methods={sorted(methods)} commit={record['code_commit']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
