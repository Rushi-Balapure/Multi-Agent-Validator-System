"""Per-split budgets and the held-out freeze gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validator.split_policy import (
    SPLIT_CLAIM_BUDGET,
    SplitPolicyError,
    assert_limit_for_split,
    assert_split_allowed,
    budget_for_split,
)


def _freeze(tmp_path: Path, **overrides) -> Path:
    payload = {
        "freeze_id": "held-out-v1",
        "model_id": "gpt-6-luna",
        "primary_metric": "false_endorsement_gold_nonsup",
        "config_hash": "a" * 64,
        "prompt_hash": "b" * 64,
        "corpus_hash": "c" * 64,
        "code_commit": "deadbeef",
    }
    payload.update(overrides)
    path = tmp_path / "freeze.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_development_budget_is_the_locked_split_size():
    assert budget_for_split("development") == 709
    assert SPLIT_CLAIM_BUDGET["held_out_local_eval"] == 300
    assert assert_limit_for_split("development", 300) == 300
    with pytest.raises(SplitPolicyError, match="exceeds"):
        assert_limit_for_split("development", 710)
    with pytest.raises(SplitPolicyError, match="positive"):
        assert_limit_for_split("development", 0)


def test_development_does_not_need_a_freeze_file():
    assert assert_split_allowed("development", frozen_final=False) is None
    with pytest.raises(SplitPolicyError, match="held-out"):
        assert_split_allowed("development", frozen_final=True)


def test_held_out_requires_matching_freeze(tmp_path: Path):
    with pytest.raises(SplitPolicyError, match="frozen-final"):
        assert_split_allowed("held_out_local_eval", frozen_final=False)
    path = _freeze(tmp_path)
    with pytest.raises(SplitPolicyError, match="freeze file"):
        assert_split_allowed(
            "held_out_local_eval",
            frozen_final=True,
            freeze_path=tmp_path / "missing.json",
        )
    record = assert_split_allowed(
        "held_out_local_eval",
        frozen_final=True,
        freeze_path=path,
        observed={
            "model_id": "gpt-6-luna",
            "config_hash": "a" * 64,
            "prompt_hash": "b" * 64,
            "corpus_hash": "c" * 64,
        },
    )
    assert record is not None
    assert record.model_id == "gpt-6-luna"
    with pytest.raises(SplitPolicyError, match="model_id"):
        assert_split_allowed(
            "held_out_local_eval",
            frozen_final=True,
            freeze_path=path,
            observed={"model_id": "other-model"},
        )
