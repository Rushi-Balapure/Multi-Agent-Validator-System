"""Locate the repository root without importing the corpus loader."""

from __future__ import annotations

import sys
from pathlib import Path


def find_repo_root() -> Path:
    """Return the checkout that holds Corpus Lock configs and manifests."""
    here = Path(__file__).resolve()
    for candidate in here.parents:
        corpus_cfg = candidate / "configs" / "corpus" / "scifact.yaml"
        manifest_dir = candidate / "manifests" / "scifact"
        if corpus_cfg.is_file() and manifest_dir.is_dir():
            return candidate
    raise RuntimeError(
        "could not locate the repository root (configs/corpus/scifact.yaml and manifests/scifact)"
    )


def ensure_repo_on_path() -> Path:
    """Put the checkout and ``src`` on ``sys.path`` so ``data`` and ``validator`` import."""
    root = find_repo_root()
    src = root / "src"
    for entry in (str(root), str(src)):
        if entry not in sys.path:
            sys.path.insert(0, entry)
    return root
