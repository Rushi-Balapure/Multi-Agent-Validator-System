"""Per-split claim budgets and the held-out freeze gate.

Development and calibration may run at any time up to the locked split
size. ``held_out_local_eval`` is refused unless ``--frozen-final`` is set
and the current config, prompt, and model hashes match ``docs/freeze.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field

SPLIT_CLAIM_BUDGET: dict[str, int] = {
    "development": 709,
    "calibration": 100,
    "held_out_local_eval": 300,
    "official_test_unlabeled": 300,
}

HELD_OUT_SPLITS = frozenset({"held_out_local_eval", "official_test_unlabeled"})
DEFAULT_FREEZE_PATH = "docs/freeze.json"
_SHA256 = r"^[a-f0-9]{64}$"


class SplitPolicyError(ValueError):
    """A split, limit, or freeze file cannot be used."""


class FreezeRecord(BaseModel):
    """Locked hashes for the one held-out run. Written in Phase 5."""

    model_config = ConfigDict(extra="allow")

    freeze_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    primary_metric: str = Field(min_length=1)
    corpus_hash: str = Field(pattern=_SHA256)
    config_hash: str | None = Field(default=None, pattern=_SHA256)
    prompt_hash: str | None = Field(default=None, pattern=_SHA256)
    code_commit: str | None = None
    methods: dict[str, dict] | None = None


def budget_for_split(split: str) -> int:
    try:
        return SPLIT_CLAIM_BUDGET[split]
    except KeyError as exc:
        raise SplitPolicyError(
            f"unknown split {split!r}; expected one of {sorted(SPLIT_CLAIM_BUDGET)}"
        ) from exc


def assert_limit_for_split(split: str, limit: int) -> int:
    """Require a positive limit that does not exceed the locked split size."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise SplitPolicyError("limit must be a positive integer")
    budget = budget_for_split(split)
    if limit > budget:
        raise SplitPolicyError(
            f"limit {limit} exceeds the {split} budget of {budget} claims"
        )
    return limit


def assert_split_allowed(
    split: str,
    *,
    frozen_final: bool,
    freeze_path: Path | None = None,
    observed: Mapping[str, str] | None = None,
) -> FreezeRecord | None:
    """Refuse held-out splits unless ``--frozen-final`` matches the freeze file.

    ``observed`` is the current run's ``model_id``, ``config_hash``,
    ``prompt_hash``, and ``corpus_hash``. When a freeze file exists those
    fields must match. Development never requires a freeze file.
    """
    if split not in SPLIT_CLAIM_BUDGET:
        raise SplitPolicyError(
            f"unknown split {split!r}; expected one of {sorted(SPLIT_CLAIM_BUDGET)}"
        )
    if split not in HELD_OUT_SPLITS:
        if frozen_final:
            raise SplitPolicyError(
                f"--frozen-final is only for held-out splits, not {split!r}"
            )
        return None
    if not frozen_final:
        raise SplitPolicyError(
            f"refusing split {split!r} without --frozen-final. "
            "The held-out 300 stays untouched until the freeze file is written."
        )
    path = freeze_path if freeze_path is not None else Path(DEFAULT_FREEZE_PATH)
    if not path.is_file():
        raise SplitPolicyError(f"--frozen-final requires a freeze file at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SplitPolicyError(f"{path} is not JSON: {exc}") from exc
    try:
        record = FreezeRecord.model_validate(raw)
    except Exception as exc:
        raise SplitPolicyError(f"{path} is not a valid freeze record: {exc}") from exc
    if observed:
        for key in ("model_id", "corpus_hash"):
            expected = getattr(record, key)
            found = observed.get(key)
            if found is not None and found != expected:
                raise SplitPolicyError(
                    f"--frozen-final {key} {found!r} does not match {path} ({expected!r})"
                )
        method = observed.get("adaptation") or observed.get("method_id")
        if record.methods and method and method in record.methods:
            locked = record.methods[method]
            for key in ("config_hash", "prompt_hash"):
                expected = locked.get(key)
                found = observed.get(key)
                if expected and found and found != expected:
                    raise SplitPolicyError(
                        f"--frozen-final {method} {key} {found!r} does not match {path}"
                    )
        else:
            for key in ("config_hash", "prompt_hash"):
                expected = getattr(record, key)
                found = observed.get(key)
                if expected and found and found != expected:
                    raise SplitPolicyError(
                        f"--frozen-final {key} {found!r} does not match {path} ({expected!r})"
                    )
    return record
