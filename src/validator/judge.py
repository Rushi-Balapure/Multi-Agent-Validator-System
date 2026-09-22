"""Claim-visible judge over a sealed reader record and D1 evidence.

The judge sees the atomic claim, the sealed evidence-only record, and the D1
bundle. It does not see gold D0 labels and it does not audit original
citations. The default fixture path uses the deterministic label policy and
does not call a model. ``validator.live_judgment`` may call a local model for
this step; a response that does not parse is not given a scientific label.
``execution_status`` is not a scientific label.
"""

from __future__ import annotations

from validator.evidence_reader import IsolationError, SealedEvidenceRecord, compute_seal
from validator.label_policy import PassageView, decide_label, evidence_span_id
from validator.retrieval.models import EvidenceBundle
from validator.schemas import (
    Claim,
    EvidenceScope,
    ExecutionStatus,
    GoldProvenance,
    Judgment,
    LabelSpace,
)


def assert_judge_boundary(
    claim: Claim,
    sealed: SealedEvidenceRecord,
    bundle: EvidenceBundle,
) -> list[PassageView]:
    """Refuse a sealed record or D1 bundle that does not belong to this claim."""
    if claim.neutral_question != sealed.neutral_question:
        raise IsolationError(
            "judge refused a sealed record whose question does not match the claim"
        )
    expected = compute_seal(sealed.neutral_question, sealed.answer, sealed.cited_span_ids)
    if sealed.seal != expected:
        raise IsolationError("judge refused a sealed evidence record that failed its seal")
    if claim.claim_id != bundle.claim_id:
        raise IsolationError("judge refused a D1 bundle for a different claim_id")

    views: list[PassageView] = []
    bundle_ids: list[str] = []
    for passage in bundle.passages:
        span = evidence_span_id(passage)
        if span is None:
            raise IsolationError("D1 passage is missing a citable span")
        bundle_ids.append(span)
        views.append(PassageView(span_id=span, text=passage.text_span))
    unknown = [span_id for span_id in sealed.cited_span_ids if span_id not in bundle_ids]
    if unknown:
        raise IsolationError(
            "sealed reader cites spans that are not in the D1 bundle: " + ", ".join(unknown)
        )
    return views


def judge_claim(
    claim: Claim,
    sealed: SealedEvidenceRecord,
    bundle: EvidenceBundle,
) -> Judgment:
    """Label the claim against D1 after checking the sealed reader record."""
    views = assert_judge_boundary(claim, sealed, bundle)
    decision = decide_label(claim.normalized_claim, views)
    return Judgment(
        claim_id=claim.claim_id,
        evidence_scope=EvidenceScope.D1,
        label_space=LabelSpace.MAVS_FOUR_WAY,
        label=decision.label.value,
        rationale_codes=list(decision.rationale_codes),
        cited_span_ids=list(decision.cited_span_ids),
        raw_scores=None,
        calibrated_probabilities=None,
        execution_status=ExecutionStatus.COMPLETED,
        uncertainty_reasons=list(decision.uncertainty_reasons),
        gold_provenance=GoldProvenance.NONE,
    )
