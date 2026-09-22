"""Interface tests for the bootstrap-by-family timer scaffold.

The module must import, expose the 2000-resample contract, and refuse to
emit a confidence interval.
"""

from __future__ import annotations

import pytest

from evaluation.bootstrap import (
    DEFAULT_N_RESAMPLES,
    FAMILY_KEYS,
    BootstrapByFamilyConfig,
    bootstrap_by_family,
    describe_bootstrap_timer,
)
from evaluation.registry import METHOD_IDS, get_formula

_INTERVAL_KEYS = {
    "ci",
    "ci_low",
    "ci_high",
    "lower",
    "upper",
    "p_value",
    "estimate",
    "point_estimate",
}


def test_default_config_matches_the_metric_contract():
    config = BootstrapByFamilyConfig()
    assert config.n_resamples == 2000
    assert DEFAULT_N_RESAMPLES == 2000
    assert config.confidence_level == 0.95
    assert config.family_key == "question_family"
    assert config.formula_id == "F-false-endorsement"
    assert config.method_ids == METHOD_IDS == ("B2", "V")
    assert "question_family" in FAMILY_KEYS
    assert "claim_family" in FAMILY_KEYS
    assert get_formula(config.formula_id).notes_path.endswith("F-false-endorsement.md")


def test_describe_bootstrap_timer_has_no_interval():
    described = describe_bootstrap_timer()
    assert described["status"] == "not_implemented"
    assert described["n_resamples"] == 2000
    assert described["interval"] is None
    assert described["formula_id"] == "F-false-endorsement"
    assert described["method_ids"] == ["B2", "V"]
    assert described["family_key"] == "question_family"
    assert described["notes_path"] == get_formula("F-false-endorsement").notes_path
    assert _INTERVAL_KEYS.isdisjoint(described)
    assert "V predictions" in described["todo"]
    floats = [value for value in described.values() if isinstance(value, float)]
    assert floats == [0.95]


def test_claim_family_config_still_has_no_interval():
    config = BootstrapByFamilyConfig(family_key="claim_family", seed=7)
    described = describe_bootstrap_timer(config)
    assert described["family_key"] == "claim_family"
    assert described["seed"] == 7
    assert described["n_resamples"] == 2000
    assert described["interval"] is None


def test_bootstrap_by_family_raises_not_implemented():
    with pytest.raises(NotImplementedError, match="not a computed confidence interval") as exc:
        bootstrap_by_family()
    text = str(exc.value)
    assert "2000" in text
    assert "V predictions" in text
    assert "[" not in text


def test_rows_do_not_produce_an_interval():
    rows = {
        "B2": [{"claim_id": "c1", "label": "SUPPORT", "label_gold": "NEI"}],
        "V": [],
    }
    described = describe_bootstrap_timer()
    assert described["interval"] is None
    with pytest.raises(NotImplementedError, match="not a computed confidence interval"):
        bootstrap_by_family(rows)


def test_unknown_method_is_rejected_before_a_result():
    with pytest.raises(ValueError, match="method_id enum"):
        BootstrapByFamilyConfig(method_ids=("B2", "B3"))
    with pytest.raises(ValueError, match="method_id enum"):
        bootstrap_by_family({"B3": []})


def test_importable_from_the_evaluation_package():
    import evaluation.bootstrap as bootstrap

    assert bootstrap.DEFAULT_N_RESAMPLES == 2000
    assert callable(bootstrap.bootstrap_by_family)
    assert callable(bootstrap.describe_bootstrap_timer)
