"""Formula id registry. Definitions live in docs/paper-assets/formulas/."""

from __future__ import annotations

from dataclasses import dataclass

FORMULA_IDS: tuple[str, ...] = (
    "F-macro-f1-4way",
    "F-native-scifact",
    "F-false-endorsement",
    "F-claim-coverage",
    "F-recall-at-k",
    "F-brier-multi",
    "F-selective-error",
    "F-latency-cost",
)

# Frozen for the V-versus-B2 harness. Ablation ids stay out of this tuple.
METHOD_IDS: tuple[str, ...] = ("B2", "V")


@dataclass(frozen=True)
class Formula:
    formula_id: str
    name: str
    notes_path: str


_REGISTRY: dict[str, Formula] = {
    "F-macro-f1-4way": Formula(
        "F-macro-f1-4way",
        "Four-way macro-F1",
        "docs/paper-assets/formulas/F-macro-f1-4way.md",
    ),
    "F-native-scifact": Formula(
        "F-native-scifact",
        "Native SciFact scores",
        "docs/paper-assets/formulas/F-native-scifact.md",
    ),
    "F-false-endorsement": Formula(
        "F-false-endorsement",
        "False endorsement",
        "docs/paper-assets/formulas/F-false-endorsement.md",
    ),
    "F-claim-coverage": Formula(
        "F-claim-coverage",
        "Claim coverage",
        "docs/paper-assets/formulas/F-claim-coverage.md",
    ),
    "F-recall-at-k": Formula(
        "F-recall-at-k",
        "Evidence Recall@k",
        "docs/paper-assets/formulas/F-recall-at-k.md",
    ),
    "F-brier-multi": Formula(
        "F-brier-multi",
        "Multiclass Brier",
        "docs/paper-assets/formulas/F-brier-multi.md",
    ),
    "F-selective-error": Formula(
        "F-selective-error",
        "Selective-use error",
        "docs/paper-assets/formulas/F-selective-error.md",
    ),
    "F-latency-cost": Formula(
        "F-latency-cost",
        "Latency / cost",
        "docs/paper-assets/formulas/F-latency-cost.md",
    ),
}


def get_formula(formula_id: str) -> Formula:
    try:
        return _REGISTRY[formula_id]
    except KeyError as exc:
        raise KeyError(f"Unknown formula_id: {formula_id}") from exc
