"""Smoke gold for Stack V fixture-report dry-run claim ids.

Synthetic e2e report ids (``scifact:900042``, ``scifact:900142``) are not in
the locked development split, so ``--join-gold development`` cannot attach
SciFact labels. This module copies the checked-in smoke map onto prediction
rows. It does not invent predicted labels and does not invent SciFact gold.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

_GOLD_FILE = Path(__file__).resolve().parent / "fixtures" / "v_fixture_report_gold.json"


class FixtureGoldError(Exception):
    """Fixture-report smoke gold cannot be attached."""


def load_v_fixture_report_gold(path: Path | None = None) -> dict[str, str]:
    gold_path = path if path is not None else _GOLD_FILE
    if not gold_path.is_file():
        raise FixtureGoldError(f"fixture gold map not found: {gold_path}")
    payload = json.loads(gold_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise FixtureGoldError(f"{gold_path}: expected a JSON object")
    labels = payload.get("labels")
    if not isinstance(labels, dict) or not labels:
        raise FixtureGoldError(f"{gold_path}: missing labels object")
    out: dict[str, str] = {}
    for claim_id, label in labels.items():
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise FixtureGoldError(f"{gold_path}: claim_id must be a non-empty string")
        if not isinstance(label, str) or label.strip().upper() not in {
            "SUPPORT",
            "REFUTE",
            "NEI",
            "CONTRADICT",
        }:
            raise FixtureGoldError(
                f"{gold_path}: gold for {claim_id!r} must be SUPPORT|REFUTE|NEI|CONTRADICT"
            )
        out[claim_id] = label.strip().upper()
    return out


def attach_v_fixture_report_gold(
    rows: Sequence[Mapping[str, Any]],
    *,
    gold_path: Path | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return copies with ``label_gold`` for known fixture-report claim ids.

    Rows that already carry gold are left unchanged. Ok rows whose claim id is
    missing from the map are refused (so a typo cannot silently drop gold).
    Failed rows may omit gold; the scorer skips them.
    """
    gold_map = load_v_fixture_report_gold(gold_path)
    updated: list[dict[str, Any]] = []
    joined = 0
    already = 0
    for row in rows:
        claim_id = row.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise FixtureGoldError("claim_id must be a non-empty string")
        copied = dict(row)
        existing = None
        for key in ("label_gold", "gold_label", "gold"):
            value = copied.get(key)
            if isinstance(value, str) and value.strip():
                existing = value.strip().upper()
                break
        if existing is not None:
            already += 1
            copied["label_gold"] = existing
            updated.append(copied)
            continue
        status = copied.get("execution_status")
        ok = status is None or status in {"ok", "completed"}
        if claim_id not in gold_map:
            if ok:
                raise FixtureGoldError(
                    f"{claim_id}: no fixture-report smoke gold; "
                    "refusing to invent a label. Use --join-gold development "
                    "only for real development claim ids."
                )
            updated.append(copied)
            continue
        copied["label_gold"] = gold_map[claim_id]
        joined += 1
        updated.append(copied)
    meta = {
        "source": str(_GOLD_FILE.relative_to(Path(__file__).resolve().parents[2]))
        if gold_path is None
        else str(gold_path),
        "n_joined": joined,
        "n_already_labeled": already,
        "n_rows": len(updated),
        "rule": "v_fixture_report_smoke_gold",
    }
    return updated, meta
