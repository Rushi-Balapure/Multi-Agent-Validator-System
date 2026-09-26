"""Holm-Bonferroni adjustment for a small family of secondary tests.

The primary metric stays unadjusted. Secondary metrics (the second
false-endorsement denominator, and later F1 / recall) are adjusted together.
"""

from __future__ import annotations

from typing import Mapping, Sequence


class HolmError(ValueError):
    """P-values cannot be Holm-adjusted."""


def holm_adjust(
    p_values: Mapping[str, float],
    *,
    alpha: float = 0.05,
) -> dict[str, dict[str, float | bool | str]]:
    """Return adjusted p-values and reject/retain decisions.

    ``p_values`` maps a metric name to an unadjusted two-sided p-value in
    ``[0, 1]``. Ties are broken by metric name so the result is deterministic.
    """
    if isinstance(alpha, bool) or not isinstance(alpha, (int, float)):
        raise HolmError("alpha must be a number")
    if not 0.0 < float(alpha) < 1.0:
        raise HolmError("alpha must be between 0 and 1")
    if not p_values:
        raise HolmError("p_values is empty")
    items: list[tuple[str, float]] = []
    for name, value in p_values.items():
        if not isinstance(name, str) or not name:
            raise HolmError("metric names must be non-empty strings")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HolmError(f"{name} p-value is not a number")
        if not 0.0 <= float(value) <= 1.0:
            raise HolmError(f"{name} p-value {value} is outside [0, 1]")
        items.append((name, float(value)))
    items.sort(key=lambda item: (item[1], item[0]))
    m = len(items)
    adjusted: dict[str, dict[str, float | bool | str]] = {}
    running = 0.0
    rejected_prefix = True
    for rank, (name, raw) in enumerate(items, start=1):
        holm_p = min(1.0, raw * (m - rank + 1))
        running = max(running, holm_p)
        adjusted_p = min(1.0, running)
        reject = rejected_prefix and adjusted_p <= alpha
        if not reject:
            rejected_prefix = False
        adjusted[name] = {
            "p_raw": raw,
            "p_holm": adjusted_p,
            "rank": rank,
            "reject": reject,
            "alpha": float(alpha),
        }
    return adjusted


def bootstrap_two_sided_p(draws: Sequence[float], observed: float) -> float:
    """Two-sided bootstrap p-value from paired-difference draws.

    ``(1 + count of |draw| >= |observed|) / (n + 1)``. A zero observed
    difference returns 1.
    """
    if not draws:
        raise HolmError("no bootstrap draws")
    if observed == 0.0:
        return 1.0
    threshold = abs(observed)
    count = sum(1 for draw in draws if abs(draw) >= threshold)
    return (1 + count) / (len(draws) + 1)
