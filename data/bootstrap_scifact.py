"""One-command SciFact bootstrap and verify.

Turing-Machine path: run from the repository root (the clone directory).

    python3 -m data.bootstrap_scifact

Runs ``data.pins.scifact.download_verify`` and then ``data.smoke_scifact_splits``.
Exits non-zero if either step fails. Does not rewrite ``LOCKED.json``,
``PIN.json``, manifests, or schemas.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

STEPS = (
    "data.pins.scifact.download_verify",
    "data.smoke_scifact_splits",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def main() -> None:
    root = repo_root()
    for module in STEPS:
        cmd = [sys.executable, "-m", module]
        print(f"+ {' '.join(cmd)}", flush=True)
        completed = subprocess.run(cmd, cwd=root)
        if completed.returncode != 0:
            print(
                f"BOOTSTRAP FAIL: {module} exited {completed.returncode}. "
                "LOCKED.json was not rewritten.",
                flush=True,
            )
            raise SystemExit(completed.returncode if completed.returncode else 1)
    print("BOOTSTRAP OK", flush=True)


if __name__ == "__main__":
    main()
