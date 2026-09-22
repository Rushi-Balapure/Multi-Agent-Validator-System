"""Fixture path for the staged judgment pipeline.

Stages, in order: blind evidence reader, claim-visible judge, D0 citation
auditor, reconciler, claim-card renderer. The reader payload is sealed before
the claim is passed to the judge. No retrieval index is built and no model
endpoint is called. Live model prompts are a later slice.

From the repository root::

    PYTHONPATH=src python3 -m validator.fixture_pipeline \\
        --fixture tests/fixtures/judgment/complete.json \\
        --output tests/fixtures/judgment/complete_verdict.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from validator.citation_auditor import CitationAudit, CitationFlag, audit_citations
from validator.evidence_reader import (
    SealedEvidenceRecord,
    read_evidence,
)
from validator.judge import judge_claim
from validator.label_policy import evidence_span_id
from validator.reconcile import Reconciliation, ReconcilerNote, reconcile
from validator.render import ClaimCard, RenderInput, render_claim_card
from validator.retrieval.models import EvidenceBundle
from validator.schemas import Claim, Evidence, Judgment, ReportVerdict


class JudgmentFixture(BaseModel):
    """One hand-built claim, its D0 citations, and a valid D1 bundle.

    ``claim_id`` uses the ``scifact:N`` shape. Fixture ids are synthetic and
    are not corpus-lock or manifest ids.
    """

    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=1)
    claim: Claim
    d0_evidence: list[Evidence]
    d1_bundle: EvidenceBundle

    @model_validator(mode="after")
    def claim_matches_bundle(self) -> JudgmentFixture:
        if self.claim.neutral_question is None or not self.claim.neutral_question.strip():
            raise ValueError("fixture claim requires neutral_question")
        if self.claim.claim_id != self.d1_bundle.claim_id:
            raise ValueError("fixture claim_id does not match the D1 bundle")
        return self


class StagedVerdict(BaseModel):
    """Verdict artifact for Eval Forge.

    ``judgments`` and ``report_verdict`` keep the section-4 contracts.
    Per-citation flags and reconciler notes are auditor and reconciler
    outputs. They are not fields on ReportVerdict: that record's JSON schema
    forbids additional properties, and this slice does not extend it.
    """

    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    judgments: list[Judgment]
    report_verdict: ReportVerdict
    citation_flags: list[CitationFlag]
    reconciler_notes: list[ReconcilerNote]
    claim_card: ClaimCard
    sealed_reader: SealedEvidenceRecord


def reader_payload(claim: Claim, bundle: EvidenceBundle) -> dict[str, Any]:
    """Build the reader input from the neutral question and D1 spans only."""
    if claim.neutral_question is None:
        raise ValueError("reader payload requires neutral_question")
    passages = []
    for passage in bundle.passages:
        span = evidence_span_id(passage)
        if span is None:
            raise ValueError("D1 passage is missing a citable span")
        passages.append(
            {
                "span_id": span,
                "doc_id": passage.doc_id,
                "text": passage.text_span,
            }
        )
    return {"neutral_question": claim.neutral_question, "passages": passages}


def run_fixture(fixture: JudgmentFixture) -> StagedVerdict:
    """Run the five stages. The claim is not an argument to the reader."""
    payload = reader_payload(fixture.claim, fixture.d1_bundle)
    sealed = read_evidence(payload)
    d1_judgment = judge_claim(fixture.claim, sealed, fixture.d1_bundle)
    audit = audit_citations(fixture.claim, fixture.d0_evidence)
    reconciliation = reconcile(fixture.claim, audit.judgment, d1_judgment)
    card = render_claim_card(
        RenderInput(
            claim=fixture.claim,
            d0_evidence=fixture.d0_evidence,
            bundle=fixture.d1_bundle,
            d0_judgment=audit.judgment,
            d1_judgment=d1_judgment,
            citation_flags=audit.flags,
            reconciliation=reconciliation,
        )
    )
    return StagedVerdict(
        fixture_id=fixture.fixture_id,
        judgments=[d1_judgment, audit.judgment],
        report_verdict=_report_verdict(fixture, audit, reconciliation, card),
        citation_flags=audit.flags,
        reconciler_notes=reconciliation.notes,
        claim_card=card,
        sealed_reader=sealed,
    )


def load_fixture(path: Path) -> JudgmentFixture:
    return JudgmentFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _report_verdict(
    fixture: JudgmentFixture,
    audit: CitationAudit,
    reconciliation: Reconciliation,
    card: ClaimCard,
) -> ReportVerdict:
    limitations = [
        "Labels describe the supplied evidence collection only, not an unrestricted scientific conclusion.",
        "This fixture run uses deterministic lexical rules. Live model prompts are a later slice and were not called.",
        "Numerical calibration is unvalidated. Raw scores and calibrated probabilities are null.",
    ]
    if audit.judgment.execution_status is not None and audit.judgment.execution_status.value != "completed":
        limitations.append(
            "The citation audit failed closed. D1 was not used to repair D0 faithfulness."
        )
    return ReportVerdict(
        claim_coverage={
            "claim_id": fixture.claim.claim_id,
            "claims_in_report": 1,
            "claims_judged": 1,
            "partial": False,
            "unchecked_spans": [],
        },
        central_claim_outcomes=[reconciliation.central_outcome.model_dump(mode="json")],
        inference_link_status=[
            link.model_dump(mode="json") for link in reconciliation.inference_links
        ],
        conflicts_d0_d1=[
            conflict.model_dump(mode="json") for conflict in reconciliation.conflicts_d0_d1
        ],
        display_explanation=card.display_text,
        limitations=limitations,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the fixture-only staged judgment pipeline and emit Verdict JSON."
    )
    parser.add_argument("--fixture", type=Path, required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Write Verdict JSON here. Omit to write it to stdout.",
    )
    args = parser.parse_args(argv)
    verdict = run_fixture(load_fixture(args.fixture))
    text = verdict.model_dump_json(indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
