"""Same-evidence baseline (research-plan B2 adaptation).

This package judges a claim against its original citations (D0) only.
It does not retrieve documents and it does not emit four-way MAVS labels.
"""

from .b2 import IsolationError, normalize_label
from .inputs import MissingEvidenceJoinError, PredictInput

__all__ = [
    "IsolationError",
    "MissingEvidenceJoinError",
    "PredictInput",
    "normalize_label",
]
