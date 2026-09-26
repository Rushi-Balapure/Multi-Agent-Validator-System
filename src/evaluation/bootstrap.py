"""Paired cluster bootstrap by question family.

The metric contract preregisters a paired V-versus-B2 comparison on
``F-false-endorsement``, resampled by question family (claim family is the
other accepted cluster key) with 2000 resamples and a 95% interval.

Resampling draws whole families with replacement, so every report and every
claim under one family travels together. Repeated stochastic runs of the same
item are not new test examples, and the interval is a percentile interval over
the drawn families, not over individual claims.

Pairing is strict. A claim enters the comparison only when every compared
method produced an execution-ok, gold-labelled row for it. Claims dropped for
a failure in any arm are counted and reported, never silently discarded, so a
method cannot look better by failing on the hard items.

Wall-clock latency and token totals remain a separate gap: Run has
``timestamps`` and ``tokens`` only, documented in
``docs/paper-assets/run_latency_token_contract.md``. This module does not
invent them.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from evaluation.registry import METHOD_IDS, get_formula
from evaluation.scorers import ENDORSEMENT_LABEL, native_false_endorsement

DEFAULT_N_RESAMPLES = 2000
DEFAULT_CONFIDENCE_LEVEL = 0.95
FAMILY_KEYS: tuple[str, ...] = ("question_family", "claim_family")
PRIMARY_FORMULA_ID = "F-false-endorsement"
PRIMARY_METRIC = "false_endorsement_gold_nonsup"
SECONDARY_METRIC = "false_endorsement_pred_sup"
_METRICS: tuple[str, ...] = (PRIMARY_METRIC, SECONDARY_METRIC)

# Each claim becomes its own cluster. Valid only when no family grouping
# exists in the data, and always recorded in the result so the paper can state
# the clustering honestly rather than implying families were used.
SINGLETON_FAMILY_SOURCE = "claim_id_singleton"
ROW_FAMILY_SOURCE = "row_field"


class BootstrapError(ValueError):
    """The paired bootstrap cannot be computed from the supplied rows."""


@dataclass(frozen=True)
class BootstrapByFamilyConfig:
    """Resample plan. ``n_resamples`` defaults to the contract value of 2000."""

    n_resamples: int = DEFAULT_N_RESAMPLES
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL
    family_key: str = "question_family"
    formula_id: str = PRIMARY_FORMULA_ID
    method_ids: tuple[str, ...] = METHOD_IDS
    seed: int | None = None
    allow_singleton_families: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.n_resamples, bool) or not isinstance(self.n_resamples, int):
            raise ValueError("n_resamples must be an integer")
        if self.n_resamples < 1:
            raise ValueError("n_resamples must be >= 1")
        if self.family_key not in FAMILY_KEYS:
            raise ValueError(
                f"family_key {self.family_key!r} must be one of {FAMILY_KEYS}"
            )
        if self.formula_id != PRIMARY_FORMULA_ID:
            raise ValueError(
                f"this module scores {PRIMARY_FORMULA_ID} only, not {self.formula_id!r}"
            )
        if tuple(self.method_ids) != METHOD_IDS:
            raise ValueError(f"method_id enum is {METHOD_IDS} only")
        if isinstance(self.confidence_level, bool) or not isinstance(self.confidence_level, float):
            raise ValueError("confidence_level must be a float")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be between 0 and 1")
        get_formula(self.formula_id)


def describe_bootstrap_timer(
    config: BootstrapByFamilyConfig | None = None,
) -> dict[str, Any]:
    """Return the resample plan only. ``interval`` is always ``None``.

    This describes what ``bootstrap_by_family`` will do. It is not a result,
    so it carries no point estimate and no bounds.
    """
    cfg = config if config is not None else BootstrapByFamilyConfig()
    return {
        "status": "configured",
        "computes": (
            "Paired percentile bootstrap over whole question families for "
            "F-false-endorsement, on claims where every compared method is "
            "execution-ok and gold-labelled."
        ),
        "n_resamples": cfg.n_resamples,
        "confidence_level": cfg.confidence_level,
        "family_key": cfg.family_key,
        "formula_id": cfg.formula_id,
        "notes_path": get_formula(cfg.formula_id).notes_path,
        "method_ids": list(cfg.method_ids),
        "seed": cfg.seed,
        "interval": None,
    }


def bootstrap_by_family(
    rows_by_method: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
    *,
    config: BootstrapByFamilyConfig | None = None,
) -> dict[str, Any]:
    """Paired percentile bootstrap by question or claim family.

    ``rows_by_method`` maps each ``method_id`` to its prediction rows. Keys must
    be within the frozen method enum. Returns per-method intervals and the
    paired difference interval for the second method minus the first.
    """
    cfg = config if config is not None else BootstrapByFamilyConfig()
    if rows_by_method is None:
        raise BootstrapError(
            "bootstrap_by_family needs prediction rows for each compared method"
        )
    unknown = sorted(set(rows_by_method) - set(METHOD_IDS))
    if unknown:
        raise ValueError(f"method_id enum is {METHOD_IDS} only, got {unknown}")
    methods = [name for name in cfg.method_ids if name in rows_by_method]
    if len(methods) < 2:
        raise BootstrapError(
            "a paired bootstrap needs rows for two methods, got "
            f"{sorted(rows_by_method)}"
        )

    indexed, dropped = _paired_claims(rows_by_method, methods)
    if not indexed:
        raise BootstrapError(
            "no claim is execution-ok and gold-labelled in every method; "
            f"dropped {dropped['total']} claims"
        )

    families, family_source = _group_families(indexed, cfg)
    family_names = sorted(families)

    observed = {
        name: _fe_for_claims(indexed, name, list(indexed))
        for name in methods
    }
    baseline, contrast = methods[0], methods[1]

    rng = random.Random(cfg.seed)
    draws: dict[str, dict[str, list[float]]] = {
        name: {metric: [] for metric in _METRICS} for name in methods
    }
    diff_draws: dict[str, list[float]] = {metric: [] for metric in _METRICS}
    for _ in range(cfg.n_resamples):
        drawn = [family_names[rng.randrange(len(family_names))] for _ in family_names]
        claim_ids: list[str] = []
        for family in drawn:
            claim_ids.extend(families[family])
        per_method = {
            name: _fe_for_claims(indexed, name, claim_ids) for name in methods
        }
        for metric in _METRICS:
            for name in methods:
                draws[name][metric].append(per_method[name][metric])
            diff_draws[metric].append(
                per_method[contrast][metric] - per_method[baseline][metric]
            )

    alpha = 1.0 - cfg.confidence_level
    from evaluation.holm import bootstrap_two_sided_p, holm_adjust

    p_raw = {
        metric: bootstrap_two_sided_p(diff_draws[metric], observed[contrast][metric] - observed[baseline][metric])
        for metric in _METRICS
    }
    # Primary stays unadjusted; Holm covers the remaining metrics plus the
    # primary only as a recorded companion, never as the decision rule.
    holm = holm_adjust({metric: p_raw[metric] for metric in _METRICS if metric != PRIMARY_METRIC})
    return {
        "status": "computed",
        "formula_id": cfg.formula_id,
        "notes_path": get_formula(cfg.formula_id).notes_path,
        "endorsement_label": ENDORSEMENT_LABEL,
        "family_key": cfg.family_key,
        "family_source": family_source,
        "n_resamples": cfg.n_resamples,
        "confidence_level": cfg.confidence_level,
        "seed": cfg.seed,
        "n_families": len(family_names),
        "n_claims_paired": len(indexed),
        "dropped_claims": dropped,
        "baseline_method": baseline,
        "contrast_method": contrast,
        "methods": {
            name: {
                metric: {
                    "point_estimate": observed[name][metric],
                    "ci_low": _percentile(draws[name][metric], alpha / 2.0),
                    "ci_high": _percentile(draws[name][metric], 1.0 - alpha / 2.0),
                }
                for metric in _METRICS
            }
            | {
                "n_false_endorsements": observed[name]["n_false_endorsements"],
                "n_gold_nonsupported": observed[name]["n_gold_nonsupported"],
                "n_predicted_supported": observed[name]["n_predicted_supported"],
            }
            for name in methods
        },
        "paired_difference": {
            metric: {
                "point_estimate": observed[contrast][metric] - observed[baseline][metric],
                "ci_low": _percentile(diff_draws[metric], alpha / 2.0),
                "ci_high": _percentile(diff_draws[metric], 1.0 - alpha / 2.0),
                "excludes_zero": _excludes_zero(
                    _percentile(diff_draws[metric], alpha / 2.0),
                    _percentile(diff_draws[metric], 1.0 - alpha / 2.0),
                ),
                "p_raw": p_raw[metric],
            }
            for metric in _METRICS
        },
        "holm": {
            "primary_metric": PRIMARY_METRIC,
            "primary_unadjusted": True,
            "secondary": holm,
        },
    }


def _paired_claims(
    rows_by_method: Mapping[str, Sequence[Mapping[str, Any]]],
    methods: Sequence[str],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """Keep claims usable in every arm. Count and report the rest."""
    from evaluation.score_predictions import _execution_ok, _gold_label, _predicted_label

    by_method: dict[str, dict[str, Mapping[str, Any]]] = {}
    for name in methods:
        seen: dict[str, Mapping[str, Any]] = {}
        for row in rows_by_method[name]:
            claim_id = row.get("claim_id")
            if not isinstance(claim_id, str) or not claim_id:
                raise BootstrapError(f"method {name} has a row without a claim_id")
            if claim_id in seen:
                raise BootstrapError(f"method {name} repeats claim_id {claim_id!r}")
            seen[claim_id] = row
        by_method[name] = seen

    shared = set.intersection(*(set(by_method[name]) for name in methods))
    union = set().union(*(set(by_method[name]) for name in methods))
    not_in_all = len(union - shared)

    indexed: dict[str, dict[str, Any]] = {}
    not_ok = 0
    unlabeled = 0
    for claim_id in sorted(shared):
        rows = [by_method[name][claim_id] for name in methods]
        if not all(_execution_ok(row) for row in rows):
            not_ok += 1
            continue
        entry: dict[str, Any] = {}
        gold_seen: set[str] = set()
        family: str | None = None
        for name, row in zip(methods, rows, strict=True):
            predicted = _predicted_label(row)
            gold = _gold_label(row)
            if predicted is None or gold is None:
                break
            gold_seen.add(gold)
            entry[name] = {"gold": gold, "pred": predicted}
            candidate = row.get("question_family") or row.get("claim_family")
            if isinstance(candidate, str) and candidate:
                family = candidate
        if len(entry) < len(methods):
            unlabeled += 1
            continue
        if len(gold_seen) > 1:
            raise BootstrapError(
                f"claim {claim_id!r} has disagreeing gold labels across methods: "
                f"{sorted(gold_seen)}"
            )
        entry["_family"] = family
        indexed[claim_id] = entry

    dropped = {
        "not_in_every_method": not_in_all,
        "execution_not_ok": not_ok,
        "unlabeled": unlabeled,
        "total": not_in_all + not_ok + unlabeled,
    }
    return indexed, dropped


def _group_families(
    indexed: Mapping[str, Mapping[str, Any]],
    cfg: BootstrapByFamilyConfig,
) -> tuple[dict[str, list[str]], str]:
    """Group paired claim ids by family, or refuse to guess the clustering."""
    families: dict[str, list[str]] = {}
    missing = [
        claim_id
        for claim_id, entry in indexed.items()
        if not isinstance(entry.get("_family"), str)
    ]
    if not missing:
        for claim_id, entry in indexed.items():
            families.setdefault(entry["_family"], []).append(claim_id)
        return families, ROW_FAMILY_SOURCE
    if not cfg.allow_singleton_families:
        raise BootstrapError(
            f"{len(missing)} paired claims carry no {cfg.family_key!r}. Supply the "
            "grouping, or pass allow_singleton_families=True to treat every claim "
            "as its own cluster. A singleton clustering narrows the interval and "
            "must be reported as such."
        )
    for claim_id in indexed:
        families[claim_id] = [claim_id]
    return families, SINGLETON_FAMILY_SOURCE


def _fe_for_claims(
    indexed: Mapping[str, Mapping[str, Any]],
    method: str,
    claim_ids: Sequence[str],
) -> dict[str, Any]:
    pairs = [
        (indexed[claim_id][method]["gold"], indexed[claim_id][method]["pred"])
        for claim_id in claim_ids
    ]
    return native_false_endorsement(pairs)


def _percentile(values: Sequence[float], quantile: float) -> float:
    """Linear-interpolated percentile of the resample distribution."""
    if not values:
        raise BootstrapError("no resamples to take a percentile from")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = quantile * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _excludes_zero(ci_low: float, ci_high: float) -> bool:
    """Whether the paired interval excludes no difference."""
    return ci_low > 0.0 or ci_high < 0.0
