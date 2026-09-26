"""Matched-budget B2@k majority vote.

``k`` is chosen so k times the mean B2 tokens per claim is at least the mean
V tokens per claim. Ties prefer NEI, then REFUTE, then SUPPORT (the
conservative order).
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Mapping, Sequence

LABEL_TIEBREAK = ("NEI", "REFUTE", "SUPPORT")


def choose_k(*, b2_tokens_per_claim: float, v_tokens_per_claim: float) -> int:
    if b2_tokens_per_claim <= 0:
        return 1
    needed = v_tokens_per_claim / b2_tokens_per_claim
    k = max(1, int(needed) if needed == int(needed) else int(needed) + 1)
    return k


def majority_label(labels: Sequence[str]) -> str:
    if not labels:
        raise ValueError("majority_label needs at least one label")
    counts = Counter(labels)
    best = counts.most_common()
    top = best[0][1]
    tied = {label for label, count in best if count == top}
    for preferred in LABEL_TIEBREAK:
        if preferred in tied:
            return preferred
    return best[0][0]


def collapse_b2k(
    rows_by_seed: Sequence[Sequence[Mapping[str, Any]]],
    *,
    k: int,
) -> list[dict[str, Any]]:
    if k < 1:
        raise ValueError("k must be at least 1")
    if len(rows_by_seed) < k:
        raise ValueError(f"need {k} B2 seeds, got {len(rows_by_seed)}")
    by_claim: dict[str, list[Mapping[str, Any]]] = {}
    for seed_rows in rows_by_seed[:k]:
        for row in seed_rows:
            by_claim.setdefault(str(row["claim_id"]), []).append(row)
    collapsed: list[dict[str, Any]] = []
    for claim_id, group in by_claim.items():
        labels = [str(row["label"]) for row in group]
        collapsed.append(
            {
                "claim_id": claim_id,
                "label": majority_label(labels),
                "adaptation": f"B2@{k}",
                "method_id": f"B2@{k}",
                "system_id": "same_evidence_baseline",
                "votes": labels,
                "k": k,
                "execution_status": "ok"
                if all(row.get("execution_status", "ok") == "ok" for row in group)
                else "failed",
                "inference_mode": group[0].get("inference_mode"),
            }
        )
    return collapsed
