"""Locate the repository root so the CLI can import ``data`` and ``validator``."""

from __future__ import annotations

import sys
from pathlib import Path


def find_repo_root() -> Path:
    """Walk parents until the corpus-lock config and loader are both present."""
    start = Path(__file__).resolve()
    for candidate in (start.parent, *start.parents):
        if (candidate / "configs" / "corpus" / "scifact.yaml").is_file() and (
            candidate / "data" / "scifact_loader.py"
        ).is_file():
            return candidate
    raise RuntimeError("could not locate the repository root from validator.retrieval")


REPO_ROOT = find_repo_root()


def _bootstrap(repo: Path) -> None:
    for entry in (str(repo), str(repo / "src")):
        if entry in sys.path:
            sys.path.remove(entry)
        sys.path.insert(0, entry)


_bootstrap(REPO_ROOT)
