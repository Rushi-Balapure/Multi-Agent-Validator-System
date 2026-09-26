"""Holm-Bonferroni adjustment."""

from __future__ import annotations

import pytest

from evaluation.holm import HolmError, bootstrap_two_sided_p, holm_adjust


def test_holm_rejects_the_smallest_and_retains_the_rest():
    adjusted = holm_adjust(
        {"fe_gold": 0.01, "fe_pred": 0.04, "macro_f1": 0.20},
        alpha=0.05,
    )
    assert adjusted["fe_gold"]["reject"] is True
    assert adjusted["fe_gold"]["p_holm"] == pytest.approx(0.03)
    assert adjusted["fe_pred"]["reject"] is False
    assert adjusted["macro_f1"]["reject"] is False


def test_holm_is_deterministic_on_ties():
    first = holm_adjust({"b": 0.02, "a": 0.02})
    second = holm_adjust({"a": 0.02, "b": 0.02})
    assert first == second
    assert first["a"]["rank"] == 1


def test_bootstrap_p_is_one_when_observed_is_zero():
    assert bootstrap_two_sided_p([0.1, -0.1, 0.0], 0.0) == 1.0


def test_bootstrap_p_counts_extreme_draws():
    draws = [0.1, 0.2, -0.05, 0.4, -0.3]
    assert bootstrap_two_sided_p(draws, 0.35) == pytest.approx((1 + 1) / 6)


def test_empty_inputs_are_errors():
    with pytest.raises(HolmError):
        holm_adjust({})
    with pytest.raises(HolmError):
        bootstrap_two_sided_p([], 0.1)
