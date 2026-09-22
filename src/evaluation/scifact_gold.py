"""Claim-level SciFact gold from the locked Corpus Lock loader.

Predictions files do not carry gold. This module copies labels from
``data.scifact_loader.load_split`` and does not invent them.

Empty evidence has no ``gold_labels``. On the B2 label space that is NEI
(the baseline's NEI-eligible case). It is not a four-way Unaddressed label.
A claim whose rationales are all SUPPORT or all CONTRADICT keeps that
token. CONTRADICT is scored later as REFUTE. Mixed SUPPORT and CONTRADICT
on one claim is refused.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

_NATIVE = frozenset({"SUPPORT", "CONTRADICT"})
_REFUSED_SPLITS = frozenset({"official_test_unlabeled"})


class GoldJoinError(Exception):
    """Locked SciFact gold cannot be attached without inventing a label."""


def claim_label_from_native(labels: Sequence[str]) -> str:
    """Reduce upstream rationale labels to one claim label.

    ``labels`` is empty when the locked evidence object is empty.
    """
    if not labels:
        return "NEI"
    unknown = [label for label in labels if label not in _NATIVE]
    if unknown:
        raise GoldJoinError(
            f"upstream gold {unknown!r} is outside SUPPORT|CONTRADICT; refusing to relabel"
        )
    unique = set(labels)
    if len(unique) != 1:
        raise GoldJoinError(
            f"mixed upstream gold {sorted(unique)}; refusing to collapse to one label"
        )
    return next(iter(unique))


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _locked_corpus_sha256(root: Path) -> str:
    pin = json.loads((root / "data" / "pins" / "scifact" / "PIN.json").read_text(encoding="utf-8"))
    return pin["files"]["corpus.jsonl"]["sha256"]


def join_scifact_gold(
    rows: Sequence[Mapping[str, Any]],
    *,
    split: str,
    sidecar: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return rows with ``label_gold`` filled from the locked split.

    Rows that already have gold are left unchanged. A sidecar ``run.split``
    or ``run.corpus_hash`` that disagrees with the lock is an error.
    """
    if split in _REFUSED_SPLITS:
        raise GoldJoinError(f"{split} has no gold labels; refusing to invent them")
    if sidecar:
        run = sidecar.get("run") if isinstance(sidecar.get("run"), Mapping) else {}
        sidecar_split = run.get("split") if isinstance(run, Mapping) else None
        if isinstance(sidecar_split, str) and sidecar_split != split:
            raise GoldJoinError(
                f"sidecar split {sidecar_split!r} does not match --join-gold {split!r}"
            )
        corpus_hash = run.get("corpus_hash") if isinstance(run, Mapping) else None
        locked = _locked_corpus_sha256(_repo_root())
        if isinstance(corpus_hash, str) and corpus_hash != locked:
            raise GoldJoinError(
                "sidecar corpus_hash does not match data/pins/scifact/PIN.json "
                f"corpus.jsonl sha256 {locked}"
            )

    from data.scifact_loader import MANIFESTS, SciFactDataError, load_split

    if split not in MANIFESTS:
        raise GoldJoinError(f"unknown locked split {split!r}")
    try:
        bundles = load_split(split)
    except SciFactDataError as exc:
        raise GoldJoinError(str(exc)) from exc
    by_id = {bundle.claim.claim_id: bundle for bundle in bundles}
    joined_rows: list[dict[str, Any]] = []
    claims: list[dict[str, Any]] = []
    n_already = 0
    for row in rows:
        claim_id = row.get("claim_id")
        if not isinstance(claim_id, str):
            raise GoldJoinError("prediction row is missing claim_id")
        existing = _existing_gold(row)
        if existing is not None:
            n_already += 1
            joined_rows.append(dict(row))
            claims.append(
                {
                    "claim_id": claim_id,
                    "label": _predicted(row),
                    "label_gold": existing,
                    "native_labels": None,
                    "gold_source": "prediction_row",
                }
            )
            continue
        try:
            bundle = by_id[claim_id]
        except KeyError as exc:
            raise GoldJoinError(
                f"{claim_id} is not in the locked {split} split; refusing to invent a label"
            ) from exc
        native = [judgment.label for judgment in bundle.gold_labels]
        label_gold = claim_label_from_native(native)
        updated = dict(row)
        updated["label_gold"] = label_gold
        joined_rows.append(updated)
        claims.append(
            {
                "claim_id": claim_id,
                "label": _predicted(row),
                "label_gold": label_gold,
                "native_labels": native,
                "gold_source": "data.scifact_loader.load_split",
            }
        )
    report = {
        "source": "data.scifact_loader.load_split",
        "split": split,
        "manifest": MANIFESTS[split],
        "rule": (
            "Upstream gold_labels only. Empty evidence (no gold_labels) is NEI "
            "on the SUPPORT/REFUTE/NEI label space, not a four-way label. "
            "Uniform SUPPORT or CONTRADICT is kept. CONTRADICT is scored as REFUTE. "
            "Mixed SUPPORT and CONTRADICT is refused."
        ),
        "n_joined": len(claims) - n_already,
        "n_already_labeled": n_already,
        "claims": claims,
    }
    return joined_rows, report


def _existing_gold(row: Mapping[str, Any]) -> str | None:
    for key in ("label_gold", "gold_label", "gold"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _predicted(row: Mapping[str, Any]) -> str | None:
    for key in ("label_pred", "predicted_label", "label"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None
