"""Map staged four-way judgments onto the Eval native label space.

The staged pipeline (``fixture_pipeline.run_report``) emits four-way labels
``supported``, ``contradicted``, ``unaddressed``, and ``underdetermined``.
``evaluation.score_predictions`` scores ``SUPPORT``, ``REFUTE``, and ``NEI``
only. This module is the only place that mapping is defined:

- ``supported`` → ``SUPPORT``
- ``contradicted`` → ``REFUTE``
- ``unaddressed`` → ``NEI``
- ``underdetermined`` → ``NEI``

The scored ``label`` is that native token. ``label_4way`` keeps the four-way
token. The token that is mapped is the reconciled ``D0_union_D1`` judgment:
agreement copies the shared four-way label, and disagreement or a failed D0
audit is ``underdetermined`` (then ``NEI``). D0 is not replaced by D1.
Unaddressed and underdetermined both become ``NEI`` because the native
SciFact space has no separate slot for those two project labels.
"""

from __future__ import annotations

NATIVE_LABELS = ("SUPPORT", "REFUTE", "NEI")
SCORED_EVIDENCE_SCOPE = "D0_union_D1"

# Four-way staged label → Eval native label. Do not add a fifth native class.
FOUR_WAY_TO_NATIVE: dict[str, str] = {
    "supported": "SUPPORT",
    "contradicted": "REFUTE",
    "unaddressed": "NEI",
    "underdetermined": "NEI",
}

LABEL_MAPPING_TEXT = (
    "supported SUPPORT\n"
    "contradicted REFUTE\n"
    "unaddressed NEI\n"
    "underdetermined NEI\n"
    f"scored_evidence_scope {SCORED_EVIDENCE_SCOPE}\n"
)


class LabelMapError(ValueError):
    """A staged label is outside the four-way set."""


def map_four_way_label(label: str) -> str:
    """Return the Eval native label for one four-way staged judgment."""
    if not isinstance(label, str):
        raise LabelMapError(f"four-way label must be a string, got {label!r}")
    try:
        return FOUR_WAY_TO_NATIVE[label]
    except KeyError as exc:
        known = ", ".join(sorted(FOUR_WAY_TO_NATIVE))
        raise LabelMapError(
            f"label {label!r} is outside the four-way set ({known})"
        ) from exc
