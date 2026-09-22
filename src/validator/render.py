"""Claim-card renderer.

Prose is filled from the structured record only. Excerpts are copied from
stored spans. Each claim-relevant explanatory sentence cites span ids from
that record. The renderer does not add findings, study metadata, or a
repaired citation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from validator.citation_auditor import CitationFlag, rollup_adequacy
from validator.label_policy import evidence_span_id, span_ids_in
from validator.reconcile import Reconciliation
from validator.retrieval.models import EvidenceBundle
from validator.schemas import Claim, Evidence, Judgment

CitationAdequacy = Literal["adequate", "inadequate", "unverifiable"]

_NEXT_CHECK = {
    "missing_required_citation": (
        "Attach the original cited spans. The citation audit has no D0 passage to check."
    ),
    "missing_provenance": (
        "Record original-citation provenance. The citation audit cannot verify this span."
    ),
    "conflicting_results": "Compare the cited passages that disagree.",
    "inconclusive_relevant_evidence": (
        "The cited passages address the claim without a resolved direction."
    ),
    "causal_overreach": "Separate association from causation using the cited passages.",
    "no_addressing_passage": "No cited passage addresses the claim in this record.",
    "citation_not_addressing": "The original citation does not address the claim.",
}


class RenderError(ValueError):
    """The card states something the structured record does not cite."""


class ClaimCard(BaseModel):
    """Reader-facing card. Fields follow the research-plan claim-card template."""

    model_config = ConfigDict(extra="forbid")

    claim: str
    evidence_verdict: str
    why: list[str]
    what_is_uncertain: str
    search_scope: str
    original_citations: CitationAdequacy
    next_useful_check: str
    display_text: str


class RenderInput(BaseModel):
    """Validated structured record. The renderer does not re-judge it."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    claim: Claim
    d0_evidence: list[Evidence]
    bundle: EvidenceBundle
    d0_judgment: Judgment
    d1_judgment: Judgment
    citation_flags: list[CitationFlag]
    reconciliation: Reconciliation


def render_claim_card(record: RenderInput) -> ClaimCard:
    """Build a claim card and refuse explanatory sentences that lack span ids."""
    spans = _span_texts(record)
    allowed = set(spans)
    why = _why_lines(record.d1_judgment, spans)
    verdict = _verdict_line(record.d1_judgment)
    uncertain = _uncertain(record)
    adequacy = rollup_adequacy(record.citation_flags)
    search = _search_scope(record.bundle)
    nxt = _next_check(record)
    reconciler = _reconciler_line(record)
    lines = [
        f"Claim: {record.claim.normalized_claim}",
        verdict,
        *why,
        f"What is uncertain: {uncertain}",
        f"Search scope: {search}",
        f"Original citations: {adequacy}.",
        reconciler,
        f"Next useful check: {nxt}",
    ]
    card = ClaimCard(
        claim=record.claim.normalized_claim,
        evidence_verdict=verdict,
        why=why,
        what_is_uncertain=uncertain,
        search_scope=search,
        original_citations=adequacy,
        next_useful_check=nxt,
        display_text="\n".join(lines),
    )
    verify_explanations(card, allowed)
    return card


def verify_explanations(card: ClaimCard, allowed_span_ids: set[str]) -> None:
    """Every explanatory sentence must cite span ids that exist on the record."""
    sentences = [card.evidence_verdict, *card.why]
    if card.why or _judgment_cites(card.evidence_verdict):
        sentences.extend(
            line for line in card.display_text.splitlines() if line.startswith("Reconciler:")
        )
        for sentence in sentences:
            found = span_ids_in(sentence)
            if not found:
                raise RenderError(
                    "claim-relevant explanatory sentence has no span id: " + sentence
                )
            unknown = [span_id for span_id in found if span_id not in allowed_span_ids]
            if unknown:
                raise RenderError(
                    "explanatory sentence cites unknown span ids: " + ", ".join(unknown)
                )
    for span_id in span_ids_in(card.display_text):
        if span_id not in allowed_span_ids:
            raise RenderError("display text cites an unknown span id: " + span_id)


def _judgment_cites(text: str) -> bool:
    return bool(span_ids_in(text))


def _verdict_line(judgment: Judgment) -> str:
    if judgment.cited_span_ids:
        cites = " ".join(f"[{span_id}]" for span_id in judgment.cited_span_ids)
        return f"Evidence verdict: {judgment.label} {cites}."
    return f"Evidence verdict: {judgment.label}."


def _why_lines(judgment: Judgment, spans: dict[str, str]) -> list[str]:
    lines: list[str] = []
    for span_id in judgment.cited_span_ids:
        text = spans.get(span_id)
        if text is None:
            raise RenderError("judgment cites a span that is not in the record: " + span_id)
        lines.append(f"Why: {text} [{span_id}]")
    return lines


def _span_texts(record: RenderInput) -> dict[str, str]:
    spans: dict[str, str] = {}
    for evidence in record.d0_evidence:
        span = evidence_span_id(evidence)
        if span is not None:
            spans[span] = evidence.text_span
    for passage in record.bundle.passages:
        span = evidence_span_id(passage)
        if span is None:
            raise RenderError("D1 passage is missing a citable span")
        spans[span] = passage.text_span
    return spans


def _uncertain(record: RenderInput) -> str:
    reasons = list(record.d1_judgment.uncertainty_reasons)
    for flag in record.citation_flags:
        reasons.extend(flag.defects)
    if record.d0_judgment.execution_status is not None and (
        record.d0_judgment.execution_status.value != "completed"
    ):
        reasons.extend(record.d0_judgment.uncertainty_reasons)
    ordered = list(dict.fromkeys(reasons))
    if not ordered:
        return "None recorded."
    return ", ".join(ordered) + "."


def _search_scope(bundle: EvidenceBundle) -> str:
    rounds = sorted({passage.retrieval_round for passage in bundle.passages})
    round_text = ", ".join(str(round_id) for round_id in rounds) or "none"
    return (
        f"corpus hash {bundle.corpus_hash}; "
        f"{len(bundle.passages)} independent passages; "
        f"retrieval round {round_text}."
    )


def _next_check(record: RenderInput) -> str:
    reasons: list[str] = []
    reasons.extend(record.d1_judgment.uncertainty_reasons)
    reasons.extend(record.d0_judgment.uncertainty_reasons)
    for flag in record.citation_flags:
        reasons.extend(flag.defects)
    for reason in reasons:
        if reason in _NEXT_CHECK:
            return _NEXT_CHECK[reason]
    return "No further check is recorded on this claim."


def _reconciler_line(record: RenderInput) -> str:
    link = record.reconciliation.inference_links[0]
    note = record.reconciliation.notes[0].note.rstrip(".")
    cites = [
        f"[{span_id}]"
        for judgment in (record.d0_judgment, record.d1_judgment)
        for span_id in judgment.cited_span_ids
    ]
    if cites:
        note = f"{note} {' '.join(cites)}"
    return f"Reconciler: {note}. Inference link: {link.status}."
