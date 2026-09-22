"""Metric scorers. Import shared prediction types when Corpus Lock lands schemas."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


SUPPORTED = "supported"


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
