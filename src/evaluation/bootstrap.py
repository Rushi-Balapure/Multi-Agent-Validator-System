"""Bootstrap-by-family timer scaffold.

The metric contract preregisters a paired V-versus-B2 comparison on
``F-false-endorsement``, resampled by question family (claim family is the
other accepted cluster key) with 2000 resamples and a 95% interval.

This module stores that plan. It does not draw resamples and it does not
return a confidence interval. Wall-clock latency and token totals are a
separate gap: Run has ``timestamps`` and ``tokens`` only, documented in
``docs/paper-assets/run_latency_token_contract.md``. Corpus Lock and Arch
Lead own those fields. This module does not invent them.

TODO: implement ``bootstrap_by_family`` once V predictions exist on the same
claim ids as B2. Until then the function raises ``NotImplementedError``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from evaluation.registry import METHOD_IDS, get_formula

DEFAULT_N_RESAMPLES = 2000
DEFAULT_CONFIDENCE_LEVEL = 0.95
FAMILY_KEYS: tuple[str, ...] = ("question_family", "claim_family")
PRIMARY_FORMULA_ID = "F-false-endorsement"

_NOT_IMPLEMENTED = (
    "TODO: bootstrap by question/claim family is not implemented until V "
    "predictions exist alongside B2 on the same claim ids. "
    "n_resamples={n_resamples} is the metric-contract default, "
    "not a computed confidence interval."
)


@dataclass(frozen=True)
class BootstrapByFamilyConfig:
    """Resample plan. ``n_resamples`` defaults to the contract value of 2000.

    ``confidence_level`` is the interval the future implementation will
    report. Constructing this object does not estimate that interval.
    """

    n_resamples: int = DEFAULT_N_RESAMPLES
    confidence_level: float = DEFAULT_CONFIDENCE_LEVEL
    family_key: str = "question_family"
    formula_id: str = PRIMARY_FORMULA_ID
    method_ids: tuple[str, ...] = METHOD_IDS
    seed: int | None = None

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
                f"this scaffold scores {PRIMARY_FORMULA_ID} only, not {self.formula_id!r}"
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
    """Return the resample plan. ``interval`` is always ``None``.

    The dict is the importable interface for the timer scaffold. It carries
    ``n_resamples`` and the family key. It has no lower bound, upper bound,
    or point estimate.
    """
    cfg = config if config is not None else BootstrapByFamilyConfig()
    return {
        "status": "not_implemented",
        "todo": (
            "Compute a paired bootstrap once V predictions exist on the same "
            "claim ids as B2. Carry each question family (or claim family) "
            "together. Do not fill an interval before that."
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
    """Paired bootstrap by question or claim family.

    TODO: draw ``config.n_resamples`` clusters once V exists. The declared
    return type is the future interval record. This body never returns it.

    ``rows_by_method`` is accepted so the call shape can be tested. Keys, when
    present, must be ``B2`` and ``V`` only. Rows are not resampled.
    """
    cfg = config if config is not None else BootstrapByFamilyConfig()
    if rows_by_method is not None:
        unknown = sorted(set(rows_by_method) - set(METHOD_IDS))
        if unknown:
            raise ValueError(f"method_id enum is {METHOD_IDS} only, got {unknown}")
    raise NotImplementedError(_NOT_IMPLEMENTED.format(n_resamples=cfg.n_resamples))
