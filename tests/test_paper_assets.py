"""Paper table/figure generators run without live artifacts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_make_tables_and_figures(tmp_path: Path, monkeypatch):
    env_python = sys.executable
    tables = subprocess.run(
        [env_python, str(ROOT / "scripts" / "paper" / "make_tables.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert tables.returncode == 0, tables.stderr
    figures = subprocess.run(
        [env_python, str(ROOT / "scripts" / "paper" / "make_figures.py")],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert figures.returncode == 0, figures.stderr
    assert (ROOT / "docs" / "paper-assets" / "tables" / "T1_main.md").is_file()
    assert (ROOT / "docs" / "paper-assets" / "graphs" / "architecture.svg").is_file()
