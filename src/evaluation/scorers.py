"""Metric scorers. Import shared prediction types when Corpus Lock lands schemas.

B2 same-evidence predictions use SciFact SUPPORT / REFUTE / NEI. On that
label space, SUPPORT is the endorsement class for F-false-endorsement
(the native counterpart of ``supported``). Four-way macro-F1 is a
different formula and is not computed here.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence


SUPPORTED = "supported"
NATIVE_LABELS: tuple[str, ...] = ("SUPPORT", "REFUTE", "NEI")
PREDICTION_LABEL_SPACE = "scifact_SUPPORT_REFUTE_NEI"
ENDORSEMENT_LABEL = "SUPPORT"

# CONTRADICT is the SciFact gold token. B2 predictions spell that class REFUTE.
_NATIVE_ALIASES = {
    "SUPPORT": "SUPPORT",
    "REFUTE": "REFUTE",
    "NEI": "NEI",
    "CONTRADICT": "REFUTE",
}


def false_endorsement(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compute F-false-endorsement with both denominators.

    Counts only rows with execution_status == \"ok\".
    Predictions that are not supported never enter the numerator.
    """
    gold_nonsup = 0
    pred_sup = 0
    false_endorsements = 0

    for row in rows:
        if row.get("execution_status") != "ok":
            continue
        gold = row["label_gold"]
        pred = row["label_pred"]
        if gold != SUPPORTED:
            gold_nonsup += 1
        if pred == SUPPORTED:
            pred_sup += 1
            if gold != SUPPORTED:
                false_endorsements += 1

    fe_gold = (false_endorsements / gold_nonsup) if gold_nonsup else 0.0
    fe_pred = (false_endorsements / pred_sup) if pred_sup else 0.0

    return {
        "formula_id": "F-false-endorsement",
        "false_endorsement_gold_nonsup": fe_gold,
        "false_endorsement_pred_sup": fe_pred,
        "n_false_endorsements": false_endorsements,
        "n_gold_nonsupported": gold_nonsup,
        "n_predicted_supported": pred_sup,
    }


def normalize_native_label(raw: Any) -> str:
    """Map a B2 or SciFact token onto SUPPORT, REFUTE, or NEI.

    ``CONTRADICT`` is accepted only as an alias of ``REFUTE``.
    """
    if not isinstance(raw, str):
        raise ValueError(f"label {raw!r} is not a string")
    token = raw.strip().upper()
    try:
        return _NATIVE_ALIASES[token]
    except KeyError as exc:
        raise ValueError(
            f"label {raw!r} is outside SciFact SUPPORT/REFUTE/NEI "
            "(CONTRADICT is accepted only as an alias of REFUTE)"
        ) from exc


def precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Per-class precision, recall, and F1. F1 is 0 when P + R is 0."""
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    if precision + recall == 0.0:
        return precision, recall, 0.0
    return precision, recall, (2 * precision * recall) / (precision + recall)


def three_way_counts(pairs: Sequence[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """Confusion counts for a fixed SUPPORT / REFUTE / NEI label set.

    ``pairs`` are ``(gold, pred)`` already normalized. Macro averages this
    full set, including classes with no gold rows.
    """
    counts = {label: {"tp": 0, "fp": 0, "fn": 0} for label in NATIVE_LABELS}
    for gold, pred in pairs:
        for label in NATIVE_LABELS:
            if pred == label and gold == label:
                counts[label]["tp"] += 1
            elif pred == label and gold != label:
                counts[label]["fp"] += 1
            elif gold == label and pred != label:
                counts[label]["fn"] += 1
    return counts


def native_false_endorsement(pairs: Sequence[tuple[str, str]]) -> dict[str, Any]:
    """F-false-endorsement with SUPPORT as the endorsement class.

    Both denominators come from ``false_endorsement``. Failures must already
    have been dropped by the caller.
    """
    rows = [
        {
            "label_gold": SUPPORTED if gold == ENDORSEMENT_LABEL else "other",
            "label_pred": SUPPORTED if pred == ENDORSEMENT_LABEL else "other",
            "execution_status": "ok",
        }
        for gold, pred in pairs
    ]
    return false_endorsement(rows)
