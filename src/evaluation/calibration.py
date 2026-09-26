"""Verbalized-confidence calibration: temperature / Platt, Brier, NLL, ECE."""

from __future__ import annotations

import math
from typing import Sequence


LABELS = ("SUPPORT", "REFUTE", "NEI")


def one_hot(label: str) -> list[float]:
    return [1.0 if item == label else 0.0 for item in LABELS]


def softmax(logits: Sequence[float], temperature: float = 1.0) -> list[float]:
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    scaled = [value / temperature for value in logits]
    peak = max(scaled)
    exps = [math.exp(value - peak) for value in scaled]
    total = sum(exps)
    return [value / total for value in exps]


def verbalized_distribution(label: str, confidence: float) -> list[float]:
    """Put ``confidence`` on ``label`` and split the remainder uniformly."""
    if not 0.0 <= confidence <= 1.0:
        raise ValueError("confidence must be in [0, 1]")
    if label not in LABELS:
        raise ValueError(f"unknown label {label!r}")
    rest = (1.0 - confidence) / (len(LABELS) - 1)
    return [confidence if item == label else rest for item in LABELS]


def brier_score(probs: Sequence[Sequence[float]], gold: Sequence[str]) -> float:
    if not gold:
        return 0.0
    total = 0.0
    for dist, label in zip(probs, gold, strict=True):
        target = one_hot(label)
        total += sum((p - t) ** 2 for p, t in zip(dist, target, strict=True))
    return total / len(gold)


def nll(probs: Sequence[Sequence[float]], gold: Sequence[str], *, eps: float = 1e-12) -> float:
    if not gold:
        return 0.0
    total = 0.0
    index = {label: i for i, label in enumerate(LABELS)}
    for dist, label in zip(probs, gold, strict=True):
        total += -math.log(max(dist[index[label]], eps))
    return total / len(gold)


def ece(
    probs: Sequence[Sequence[float]],
    gold: Sequence[str],
    *,
    n_bins: int = 10,
) -> float:
    if not gold:
        return 0.0
    index = {label: i for i, label in enumerate(LABELS)}
    bins = [[] for _ in range(n_bins)]
    for dist, label in zip(probs, gold, strict=True):
        confidence = max(dist)
        predicted = LABELS[dist.index(confidence)]
        correct = 1.0 if predicted == label else 0.0
        slot = min(n_bins - 1, int(confidence * n_bins))
        bins[slot].append((confidence, correct))
    error = 0.0
    n = len(gold)
    for bucket in bins:
        if not bucket:
            continue
        conf = sum(item[0] for item in bucket) / len(bucket)
        acc = sum(item[1] for item in bucket) / len(bucket)
        error += (len(bucket) / n) * abs(acc - conf)
    return error


def fit_temperature(probs: Sequence[Sequence[float]], gold: Sequence[str]) -> float:
    """Grid-search a positive temperature that minimizes NLL."""
    best_t = 1.0
    best = float("inf")
    logits_list = [[math.log(max(p, 1e-12)) for p in dist] for dist in probs]
    for step in range(1, 41):
        temperature = step / 10.0
        calibrated = [softmax(logits, temperature) for logits in logits_list]
        score = nll(calibrated, gold)
        if score < best:
            best = score
            best_t = temperature
    return best_t


def apply_temperature(probs: Sequence[Sequence[float]], temperature: float) -> list[list[float]]:
    return [softmax([math.log(max(p, 1e-12)) for p in dist], temperature) for dist in probs]
