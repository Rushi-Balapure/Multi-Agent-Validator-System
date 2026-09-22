"""Offline Phase-1 smoke: synthetic B2 dry-run plus the Eval Forge fixture score."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / "data" / "pins" / "scifact" / "PIN.json"
LOCKED = ROOT / "data" / "pins" / "scifact" / "LOCKED.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_phase1_smoke_exits_zero_offline(tmp_path: Path):
    pin_before = _sha256(PIN)
    locked_before = _sha256(LOCKED)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["PHASE1_SMOKE_OUT"] = str(tmp_path / "phase1_smoke")
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "phase1_smoke.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "phase1 smoke OK" in proc.stdout
    assert "download" not in proc.stdout.lower() or "no download" in proc.stdout.lower()
    out = Path(env["PHASE1_SMOKE_OUT"])
    rows = [
        json.loads(line)
        for line in (out / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    assert rows[0]["inference_mode"] == "mock"
    assert rows[0]["claim_id"] == "example:vitamin-tablet"
    assert rows[0]["label"] in {"SUPPORT", "REFUTE", "NEI"}
    sidecar = json.loads((out / "run.json").read_text(encoding="utf-8"))
    assert sidecar["inference_mode"] == "mock"
    assert sidecar["model_invoked"] is False
    assert sidecar["dry_run"] is True
    report = json.loads((out / "metrics.json").read_text(encoding="utf-8"))
    expected = json.loads(
        (ROOT / "src" / "evaluation" / "fixtures" / "b2_metrics_expected.json").read_text(encoding="utf-8")
    )
    assert {key: report[key] for key in expected} == expected
    assert report["n_scored"] == 8
    assert _sha256(PIN) == pin_before
    assert _sha256(LOCKED) == locked_before
    assert "python3 -m data.pins.scifact.download_verify" not in (ROOT / "scripts" / "phase1_smoke.sh").read_text(
        encoding="utf-8"
    )
    assert sys.version_info >= (3, 11)
