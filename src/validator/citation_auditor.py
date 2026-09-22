"""Citation auditor for the original citation set (D0).

Inputs are the atomic claim and D0 evidence. The auditor does not read D1
and does not repair an unfaithful citation with independent evidence. An
empty or span-less citation set is an explicit audit failure: the judgment
stays a four-way scientific label, and ``execution_status`` carries the failure.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from validator.evidence_reader import IsolationError
from validator.label_policy import PassageView, decide_label, evidence_span_id
from validator.schemas import (
    AccessScope,
    Claim,
    Evidence,
    EvidenceScope,
    ExecutionStatus,
    GoldProvenance,
    Judgment,
    LabelSpace,
    Provenance,
    ScientificLabel,
)

CitationAdequacy = Literal["adequate", "inadequate", "unverifiable"]


class CitationFlag(BaseModel):
    """One original citation, or a single flag when the citation set is missing."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    span_id: str | None = None
    doc_id: int | str | None = None
    adequacy: CitationAdequacy
    defects: list[str] = Field(default_factory=list)


class CitationAudit(BaseModel):
    """D0 judgment plus per-citation flags. D1 is not a field."""

    model_config = ConfigDict(extra="forbid")

    judgment: Judgment
    flags: list[CitationFlag]


def audit_citations(claim: Claim, d0_evidence: list[Evidence]) -> CitationAudit:
    """Judge citation faithfulness from D0 alone."""
    if not isinstance(d0_evidence, list):
        raise IsolationError("citation auditor accepts only a list of D0 evidence")
    for evidence in d0_evidence:
        if not isinstance(evidence, Evidence):
            raise IsolationError("citation auditor accepts only Evidence records")
        if evidence.access_scope is not AccessScope.D0:
            raise IsolationError(
                "citation auditor refuses evidence outside access_scope D0"
            )
        if evidence.provenance not in {Provenance.ORIGINAL, None}:
            raise IsolationError(
                "citation auditor refuses provenance other than original"
            )

    if not d0_evidence:
        return _failed_audit(claim, reason="missing_required_citation")

    flags: list[CitationFlag] = []
    usable: list[PassageView] = []
    failed = False
    for evidence in d0_evidence:
        span = evidence_span_id(evidence)
        if span is None or evidence.provenance is not Provenance.ORIGINAL:
            failed = True
            defects = []
            if span is None:
                defects.append("missing_required_citation")
            if evidence.provenance is not Provenance.ORIGINAL:
                defects.append("missing_provenance")
            flags.append(
                CitationFlag(
                    claim_id=claim.claim_id,
                    span_id=span,
                    doc_id=evidence.doc_id,
                    adequacy="inadequate",
                    defects=defects,
                )
            )
            continue
        view = PassageView(span_id=span, text=evidence.text_span)
        usable.append(view)
        flags.append(_flag_for_passage(claim, evidence, view))

    if not usable:
        return _failed_audit(claim, reason="missing_required_citation", flags=flags)

    decision = decide_label(claim.normalized_claim, usable)
    return CitationAudit(
        judgment=Judgment(
            claim_id=claim.claim_id,
            evidence_scope=EvidenceScope.D0,
            label_space=LabelSpace.MAVS_FOUR_WAY,
            label=decision.label.value,
            rationale_codes=list(decision.rationale_codes),
            cited_span_ids=list(decision.cited_span_ids),
            raw_scores=None,
            calibrated_probabilities=None,
            execution_status=(
                ExecutionStatus.FAILED if failed else ExecutionStatus.COMPLETED
            ),
            uncertainty_reasons=list(decision.uncertainty_reasons),
            gold_provenance=GoldProvenance.NONE,
        ),
        flags=flags,
    )


def rollup_adequacy(flags: list[CitationFlag]) -> CitationAdequacy:
    """Worst citation status: inadequate, then unverifiable, then adequate."""
    if not flags or any(flag.adequacy == "inadequate" for flag in flags):
        return "inadequate"
    if any(flag.adequacy == "unverifiable" for flag in flags):
        return "unverifiable"
    return "adequate"


def _flag_for_passage(claim: Claim, evidence: Evidence, view: PassageView) -> CitationFlag:
    decision = decide_label(claim.normalized_claim, [view])
    if decision.label is ScientificLabel.SUPPORTED:
        adequacy: CitationAdequacy = "adequate"
        defects: list[str] = []
    elif decision.label is ScientificLabel.UNDERDETERMINED:
        adequacy = "unverifiable"
        defects = list(decision.rationale_codes)
    else:
        adequacy = "inadequate"
        defects = list(decision.rationale_codes)
    return CitationFlag(
        claim_id=claim.claim_id,
        span_id=view.span_id,
        doc_id=evidence.doc_id,
        adequacy=adequacy,
        defects=defects,
    )


def _failed_audit(
    claim: Claim,
    *,
    reason: str,
    flags: list[CitationFlag] | None = None,
) -> CitationAudit:
    failure_flags = flags or [
        CitationFlag(
            claim_id=claim.claim_id,
            span_id=None,
            doc_id=None,
            adequacy="inadequate",
            defects=[reason],
        )
    ]
    return CitationAudit(
        judgment=Judgment(
            claim_id=claim.claim_id,
            evidence_scope=EvidenceScope.D0,
            label_space=LabelSpace.MAVS_FOUR_WAY,
            label=ScientificLabel.UNADDRESSED.value,
            rationale_codes=[reason],
            cited_span_ids=[],
            raw_scores=None,
            calibrated_probabilities=None,
            execution_status=ExecutionStatus.FAILED,
            uncertainty_reasons=[reason],
            gold_provenance=GoldProvenance.NONE,
        ),
        flags=failure_flags,
    )
