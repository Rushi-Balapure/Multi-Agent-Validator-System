"""Reconcile a D0 citation judgment with a D1 independent judgment.

The reconciler explains conflicts. It does not replace the D0 label with the
D1 label. Inference links are valid, invalid, or unresolved. Supported
premises are not treated as proof of an undeclared causal or transitive step.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from validator.schemas import Claim, ExecutionStatus, Judgment

InferenceStatus = Literal["valid", "invalid", "unresolved"]


class ReconcilerNote(BaseModel):
    """One plain-language note derived from the two judgments."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    note: str = Field(min_length=1)


class InferenceLink(BaseModel):
    """Status of the claim's inference link. Not a fifth scientific label."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    depends_on: list[str]
    status: InferenceStatus
    note: str


class ScopeConflict(BaseModel):
    """A recorded difference between the D0 judgment and the D1 judgment."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    d0_label: str
    d1_label: str
    d0_execution_status: ExecutionStatus
    d1_execution_status: ExecutionStatus
    note: str


class CentralClaimOutcome(BaseModel):
    """Both scope labels. ``agreed_label`` is set only when the scopes agree."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    central: bool = True
    d0_label: str
    d1_label: str
    agreed_label: str | None = None


class Reconciliation(BaseModel):
    """Reconciler output copied onto the report verdict and the artifact."""

    model_config = ConfigDict(extra="forbid")

    notes: list[ReconcilerNote]
    inference_links: list[InferenceLink]
    conflicts_d0_d1: list[ScopeConflict]
    central_outcome: CentralClaimOutcome


def reconcile(claim: Claim, d0: Judgment, d1: Judgment) -> Reconciliation:
    """Compare the two scope judgments for one atomic claim."""
    if d0.claim_id != claim.claim_id or d1.claim_id != claim.claim_id:
        raise ValueError("reconciler judgments must use the claim_id")
    if d0.evidence_scope.value != "D0" or d1.evidence_scope.value != "D1":
        raise ValueError("reconciler expects one D0 judgment and one D1 judgment")

    notes: list[ReconcilerNote] = []
    conflicts: list[ScopeConflict] = []
    if d0.label == d1.label and _completed(d0) and _completed(d1):
        notes.append(
            ReconcilerNote(
                code="labels_agree",
                note=(
                    f"D0 and D1 both assign {d0.label}, "
                    "and no D0 versus D1 conflict is recorded."
                ),
            )
        )
    else:
        note = (
            f"D0 assigns {d0.label} ({_status(d0)}) and D1 assigns {d1.label} "
            f"({_status(d1)}), and independent evidence is not used to repair "
            "the original citation."
        )
        notes.append(ReconcilerNote(code="d0_d1_conflict", note=note))
        conflicts.append(
            ScopeConflict(
                claim_id=claim.claim_id,
                d0_label=d0.label,
                d1_label=d1.label,
                d0_execution_status=_required_status(d0),
                d1_execution_status=_required_status(d1),
                note=note,
            )
        )

    status, link_note = _inference_status(claim, d0, d1)
    notes.append(ReconcilerNote(code=f"inference_link_{status}", note=link_note))
    agreed = d0.label if d0.label == d1.label and _completed(d0) and _completed(d1) else None
    return Reconciliation(
        notes=notes,
        inference_links=[
            InferenceLink(
                claim_id=claim.claim_id,
                depends_on=list(claim.dependencies),
                status=status,
                note=link_note,
            )
        ],
        conflicts_d0_d1=conflicts,
        central_outcome=CentralClaimOutcome(
            claim_id=claim.claim_id,
            d0_label=d0.label,
            d1_label=d1.label,
            agreed_label=agreed,
        ),
    )


def _inference_status(claim: Claim, d0: Judgment, d1: Judgment) -> tuple[InferenceStatus, str]:
    if not _completed(d0) or not _completed(d1):
        return (
            "unresolved",
            "An execution failure is recorded, so the inference link is unresolved. "
            "D1 is not used to repair D0.",
        )
    if claim.dependencies:
        return (
            "unresolved",
            "Dependencies are declared but premise judgments are not in this record. "
            "Supported premises do not prove a causal or transitive conclusion, "
            "so the inference link is unresolved.",
        )
    reasons = set(d0.rationale_codes) | set(d1.rationale_codes)
    if "causal_overreach" in reasons:
        return (
            "invalid",
            "The claim uses causal language and the recorded evidence does not. "
            "The inference link is invalid.",
        )
    if {d0.label, d1.label} == {"supported", "contradicted"}:
        return (
            "invalid",
            "D0 and D1 assign opposite labels, so the inference from the original "
            "citations does not hold under independent evidence. The inference link "
            "is invalid.",
        )
    if d0.label != d1.label or d0.label in {"unaddressed", "underdetermined"}:
        return (
            "unresolved",
            "The recorded labels do not resolve the claim, so the inference link "
            "is unresolved.",
        )
    if d0.label == "contradicted":
        return (
            "invalid",
            "Both scopes contradict the claim, so the inference to that conclusion "
            "is invalid.",
        )
    return (
        "valid",
        "No dependency was declared. Both completed judgments support the atomic "
        "claim, so the inference link is valid. This does not add a causal or "
        "transitive conclusion.",
    )


def _completed(judgment: Judgment) -> bool:
    return judgment.execution_status is ExecutionStatus.COMPLETED


def _required_status(judgment: Judgment) -> ExecutionStatus:
    if judgment.execution_status is None:
        return ExecutionStatus.FAILED
    return judgment.execution_status


def _status(judgment: Judgment) -> str:
    return _required_status(judgment).value
