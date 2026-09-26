"""Paired cluster bootstrap by family.

The module must expose the 2000-resample contract, compute a percentile
interval over whole families, pair strictly on claim ids, count every dropped
claim, and refuse to guess a clustering it was not given.
"""

from __future__ import annotations

import pytest

from evaluation.bootstrap import (
    DEFAULT_N_RESAMPLES,
    FAMILY_KEYS,
    ROW_FAMILY_SOURCE,
    SINGLETON_FAMILY_SOURCE,
    BootstrapByFamilyConfig,
    BootstrapError,
    bootstrap_by_family,
    describe_bootstrap_timer,
)
from evaluation.registry import METHOD_IDS, get_formula

PRIMARY = "false_endorsement_gold_nonsup"


def _row(claim_id: str, pred: str, gold: str, **extra):
    row = {
        "claim_id": claim_id,
        "label": pred,
        "label_gold": gold,
        "execution_status": "ok",
    }
    row.update(extra)
    return row


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


def test_describe_bootstrap_timer_is_a_plan_not_a_result():
    described = describe_bootstrap_timer()
    assert described["status"] == "configured"
    assert described["n_resamples"] == 2000
    assert described["interval"] is None
    assert described["formula_id"] == "F-false-endorsement"
    assert described["method_ids"] == ["B2", "V"]
    assert described["family_key"] == "question_family"
    assert described["notes_path"] == get_formula("F-false-endorsement").notes_path
    # A plan description must not carry bounds or an estimate.
    assert {"ci_low", "ci_high", "point_estimate"}.isdisjoint(described)


def test_unknown_method_is_rejected():
    with pytest.raises(ValueError, match="method_id enum"):
        BootstrapByFamilyConfig(method_ids=("B2", "B3"))
    with pytest.raises(ValueError, match="method_id enum"):
        bootstrap_by_family({"B3": []})


def test_needs_two_methods_to_pair():
    with pytest.raises(BootstrapError, match="two methods"):
        bootstrap_by_family({"B2": [_row("c1", "SUPPORT", "NEI")]})
    with pytest.raises(BootstrapError, match="needs prediction rows"):
        bootstrap_by_family()


def test_missing_family_is_refused_rather_than_guessed():
    rows = {
        "B2": [_row("c1", "SUPPORT", "NEI"), _row("c2", "NEI", "NEI")],
        "V": [_row("c1", "NEI", "NEI"), _row("c2", "NEI", "NEI")],
    }
    with pytest.raises(BootstrapError, match="allow_singleton_families"):
        bootstrap_by_family(rows)


def test_singleton_clustering_is_recorded_when_explicitly_allowed():
    rows = {
        "B2": [_row("c1", "SUPPORT", "NEI"), _row("c2", "NEI", "NEI")],
        "V": [_row("c1", "NEI", "NEI"), _row("c2", "NEI", "NEI")],
    }
    result = bootstrap_by_family(
        rows,
        config=BootstrapByFamilyConfig(
            n_resamples=200, seed=1, allow_singleton_families=True
        ),
    )
    assert result["family_source"] == SINGLETON_FAMILY_SOURCE
    assert result["n_families"] == 2
    assert result["n_claims_paired"] == 2


def test_families_group_claims_together():
    rows = {
        "B2": [
            _row("c1", "SUPPORT", "NEI", question_family="f1"),
            _row("c2", "SUPPORT", "NEI", question_family="f1"),
            _row("c3", "NEI", "NEI", question_family="f2"),
        ],
        "V": [
            _row("c1", "NEI", "NEI", question_family="f1"),
            _row("c2", "NEI", "NEI", question_family="f1"),
            _row("c3", "NEI", "NEI", question_family="f2"),
        ],
    }
    result = bootstrap_by_family(
        rows, config=BootstrapByFamilyConfig(n_resamples=500, seed=3)
    )
    assert result["family_source"] == ROW_FAMILY_SOURCE
    assert result["n_families"] == 2
    assert result["n_claims_paired"] == 3
    # B2 endorses two gold-NEI claims; V endorses none.
    assert result["methods"]["B2"][PRIMARY]["point_estimate"] == pytest.approx(2 / 3)
    assert result["methods"]["V"][PRIMARY]["point_estimate"] == 0.0
    assert result["paired_difference"][PRIMARY]["point_estimate"] == pytest.approx(-2 / 3)


def test_interval_brackets_the_point_estimate_and_is_deterministic():
    rows = {
        "B2": [
            _row(f"c{i}", "SUPPORT" if i % 2 else "NEI", "NEI", question_family=f"f{i % 5}")
            for i in range(20)
        ],
        "V": [
            _row(f"c{i}", "NEI", "NEI", question_family=f"f{i % 5}")
            for i in range(20)
        ],
    }
    config = BootstrapByFamilyConfig(n_resamples=1000, seed=11)
    first = bootstrap_by_family(rows, config=config)
    second = bootstrap_by_family(rows, config=config)
    assert first == second
    b2 = first["methods"]["B2"][PRIMARY]
    assert b2["ci_low"] <= b2["point_estimate"] <= b2["ci_high"]
    assert 0.0 <= b2["ci_low"] <= 1.0
    assert 0.0 <= b2["ci_high"] <= 1.0


def test_a_failed_row_in_either_arm_drops_the_pair_and_is_counted():
    rows = {
        "B2": [
            _row("c1", "SUPPORT", "NEI", question_family="f1"),
            _row("c2", "NEI", "NEI", question_family="f1"),
        ],
        "V": [
            dict(_row("c1", "NEI", "NEI", question_family="f1"), execution_status="failed"),
            _row("c2", "NEI", "NEI", question_family="f1"),
        ],
    }
    result = bootstrap_by_family(
        rows, config=BootstrapByFamilyConfig(n_resamples=100, seed=5)
    )
    assert result["n_claims_paired"] == 1
    assert result["dropped_claims"]["execution_not_ok"] == 1
    assert result["dropped_claims"]["total"] == 1


def test_claims_missing_from_one_arm_are_counted_not_ignored():
    rows = {
        "B2": [
            _row("c1", "NEI", "NEI", question_family="f1"),
            _row("c2", "NEI", "NEI", question_family="f1"),
        ],
        "V": [_row("c1", "NEI", "NEI", question_family="f1")],
    }
    result = bootstrap_by_family(
        rows, config=BootstrapByFamilyConfig(n_resamples=100, seed=5)
    )
    assert result["n_claims_paired"] == 1
    assert result["dropped_claims"]["not_in_every_method"] == 1


def test_no_usable_pair_refuses_rather_than_returning_zero():
    rows = {
        "B2": [dict(_row("c1", "SUPPORT", "NEI"), execution_status="failed")],
        "V": [dict(_row("c1", "NEI", "NEI"), execution_status="failed")],
    }
    with pytest.raises(BootstrapError, match="execution-ok"):
        bootstrap_by_family(rows)


def test_disagreeing_gold_across_methods_is_an_error():
    rows = {
        "B2": [_row("c1", "NEI", "SUPPORT", question_family="f1")],
        "V": [_row("c1", "NEI", "NEI", question_family="f1")],
    }
    with pytest.raises(BootstrapError, match="disagreeing gold"):
        bootstrap_by_family(rows)


def test_duplicate_claim_id_is_rejected():
    rows = {
        "B2": [_row("c1", "NEI", "NEI"), _row("c1", "NEI", "NEI")],
        "V": [_row("c1", "NEI", "NEI")],
    }
    with pytest.raises(BootstrapError, match="repeats claim_id"):
        bootstrap_by_family(rows)


def test_importable_from_the_evaluation_package():
    import evaluation.bootstrap as bootstrap

    assert bootstrap.DEFAULT_N_RESAMPLES == 2000
    assert callable(bootstrap.bootstrap_by_family)
    assert callable(bootstrap.describe_bootstrap_timer)
