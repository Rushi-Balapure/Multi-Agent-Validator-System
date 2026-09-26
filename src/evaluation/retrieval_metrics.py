"""D1 recall@k and D0/D1 document overlap."""

from __future__ import annotations

from typing import Iterable, Mapping, Sequence


def recall_at_k(
    retrieved_doc_ids: Sequence[int],
    gold_doc_ids: Sequence[int],
    *,
    k: int,
) -> float:
    if k < 1:
        raise ValueError("k must be at least 1")
    gold = set(gold_doc_ids)
    if not gold:
        return 0.0
    hit = set(retrieved_doc_ids[:k]) & gold
    return len(hit) / len(gold)


def mean_recall_at_k(
    rows: Sequence[Mapping[str, Sequence[int]]],
    *,
    k: int,
    retrieved_key: str = "d1_doc_ids",
    gold_key: str = "gold_doc_ids",
) -> dict[str, float | int]:
    values = [
        recall_at_k(row[retrieved_key], row[gold_key], k=k)
        for row in rows
        if row.get(gold_key)
    ]
    return {
        "formula_id": "F-recall-at-k",
        "k": k,
        "n": len(values),
        "recall_at_k": (sum(values) / len(values)) if values else 0.0,
    }


def document_overlap(
    d0_doc_ids: Iterable[int],
    d1_doc_ids: Iterable[int],
) -> dict[str, float | int]:
    d0 = set(d0_doc_ids)
    d1 = set(d1_doc_ids)
    inter = d0 & d1
    union = d0 | d1
    return {
        "n_d0": len(d0),
        "n_d1": len(d1),
        "n_overlap": len(inter),
        "jaccard": (len(inter) / len(union)) if union else 0.0,
    }
