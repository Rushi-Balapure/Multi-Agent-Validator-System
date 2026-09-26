"""SciFact official abstract-level, label-only adapter.

Sentence-level evidence selection is out of scope. This writes the official
prediction objects with empty ``predicted_evidence`` and scores label
agreement only: a claim is correct when the predicted SUPPORT / CONTRADICT /
NOT ENOUGH INFO token matches gold. CONTRADICT gold is the official name
for REFUTE predictions.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from evaluation.scorers import normalize_native_label
from validator.retrieve import native_id_from_claim_id

_TO_OFFICIAL = {"SUPPORT": "SUPPORT", "REFUTE": "CONTRADICT", "NEI": "NOT ENOUGH INFO"}
_FROM_GOLD = {"SUPPORT": "SUPPORT", "CONTRADICT": "CONTRADICT", "REFUTE": "CONTRADICT", "NEI": "NOT ENOUGH INFO"}


def to_official_prediction(row: Mapping[str, Any]) -> dict[str, Any]:
    claim_id = row["claim_id"]
    native_id = native_id_from_claim_id(str(claim_id))
    predicted = normalize_native_label(row.get("label") or row.get("predicted_label"))
    return {
        "id": native_id,
        "predicted_label": _TO_OFFICIAL[predicted],
        "predicted_evidence": {},
    }


def official_label_only_scores(
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Accuracy and per-class recall on official label names."""
    n = 0
    correct = 0
    gold_counts = {"SUPPORT": 0, "CONTRADICT": 0, "NOT ENOUGH INFO": 0}
    pred_correct = {"SUPPORT": 0, "CONTRADICT": 0, "NOT ENOUGH INFO": 0}
    for row in rows:
        gold_raw = row.get("label_gold") or row.get("gold_label")
        if gold_raw is None:
            continue
        gold = _FROM_GOLD[normalize_native_label(gold_raw)]
        pred = _TO_OFFICIAL[normalize_native_label(row.get("label") or row.get("predicted_label"))]
        n += 1
        gold_counts[gold] += 1
        if pred == gold:
            correct += 1
            pred_correct[gold] += 1
    recalls = {
        label: (pred_correct[label] / gold_counts[label]) if gold_counts[label] else 0.0
        for label in gold_counts
    }
    return {
        "formula_id": "F-native-scifact",
        "level": "abstract_label_only",
        "n_scored": n,
        "accuracy": (correct / n) if n else 0.0,
        "per_class_recall": recalls,
        "gold_counts": gold_counts,
        "note": "Sentence-level evidence selection is not scored.",
    }
