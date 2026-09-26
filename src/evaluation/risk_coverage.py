"""Risk-coverage curve from verbalized or calibrated confidence."""

from __future__ import annotations

from typing import Sequence


def risk_coverage_curve(
    correct: Sequence[bool],
    confidence: Sequence[float],
) -> list[dict[str, float]]:
    """Coverage vs error after dropping the least-confident predictions."""
    if len(correct) != len(confidence):
        raise ValueError("correct and confidence must be the same length")
    if not correct:
        return []
    order = sorted(range(len(correct)), key=lambda i: confidence[i], reverse=True)
    kept_correct = 0
    points: list[dict[str, float]] = []
    for rank, index in enumerate(order, start=1):
        kept_correct += 1 if correct[index] else 0
        coverage = rank / len(correct)
        accuracy = kept_correct / rank
        points.append(
            {
                "coverage": coverage,
                "accuracy": accuracy,
                "error": 1.0 - accuracy,
                "threshold": confidence[index],
            }
        )
    return points


def selective_accuracy(correct: Sequence[bool], confidence: Sequence[float], *, threshold: float) -> dict[str, float]:
    selected = [ok for ok, conf in zip(correct, confidence, strict=True) if conf >= threshold]
    n = len(correct)
    k = len(selected)
    return {
        "threshold": threshold,
        "coverage": (k / n) if n else 0.0,
        "accuracy": (sum(1 for ok in selected if ok) / k) if k else 0.0,
        "n_selected": float(k),
    }
