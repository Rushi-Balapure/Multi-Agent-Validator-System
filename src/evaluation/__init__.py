"""Evaluation package: metric registry, scorers, bootstrap (Eval Forge)."""

from src.evaluation.bootstrap import (
    DEFAULT_N_RESAMPLES,
    BootstrapByFamilyConfig,
    bootstrap_by_family,
    describe_bootstrap_timer,
)
from src.evaluation.harness import compare_false_endorsement
from src.evaluation.registry import FORMULA_IDS, METHOD_IDS, get_formula

__all__ = [
    "DEFAULT_N_RESAMPLES",
    "FORMULA_IDS",
    "METHOD_IDS",
    "BootstrapByFamilyConfig",
    "bootstrap_by_family",
    "compare_false_endorsement",
    "describe_bootstrap_timer",
    "get_formula",
]
