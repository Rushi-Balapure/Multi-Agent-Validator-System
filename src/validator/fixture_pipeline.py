"""Fixture path for the staged judgment pipeline.

Stages, in order: blind evidence reader, claim-visible judge, D0 citation
auditor, reconciler, claim-card renderer. The reader payload is sealed before
the claim is passed to the judge. No retrieval index is built.

The default path is offline. It uses the deterministic label policy and does
not call a model. ``--live`` is optional and is not used by pytest. It sends
one fixture claim to an OpenAI-compatible server on loopback or an RFC1918
host. The committed default is LM Studio:

    base_url: http://127.0.0.1:1234/v1
    model_id: qwen2.5-coder-1.5b-instruct

``http://192.168.1.10:1234/v1`` is an allowed private-LAN example. Public
hosts are refused. If the live response does not parse, the D1 judgment is
``execution_status: failed`` and the process exits 1. The model text is not
turned into a scientific label.

From the repository root::

    PYTHONPATH=src python3 -m validator.fixture_pipeline \\
        --fixture tests/fixtures/judgment/complete.json \\
        --output tests/fixtures/judgment/complete_verdict.json

    PYTHONPATH=src python3 -m validator.fixture_pipeline \\
        --fixture tests/fixtures/judgment/complete.json --live
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
from validator.inference_client import DEFAULT_BASE_URL, DEFAULT_MODEL_ID
from validator.judge import judge_claim
from validator.label_policy import evidence_span_id
from validator.live_judgment import (
    EndpointPolicyError,
    LiveConfigError,
    LoadedLive,
    default_live_config,
    load_live_settings,
    run_live_d1,
)
from validator.reconcile import Reconciliation, ReconcilerNote, reconcile
from validator.render import ClaimCard, RenderInput, render_claim_card
from validator.retrieval.models import EvidenceBundle
from validator.same_evidence._repo import find_repo_root
from validator.schemas import Claim, Evidence, EvidenceScope, ExecutionStatus, Judgment, ReportVerdict

_OFFLINE_LIMITATION = (
    "This fixture run uses deterministic lexical rules. "
    "Live model prompts are a later slice and were not called."
)


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


def run_fixture(
    fixture: JudgmentFixture,
    *,
    live: LoadedLive | None = None,
    client: Any = None,
) -> StagedVerdict:
    """Run the five stages. The claim is not an argument to the reader.

    ``live`` is omitted for the offline path. A client is only used with
    ``live``; tests pass a fake so the default path never opens a socket.
    """
    payload = reader_payload(fixture.claim, fixture.d1_bundle)
    if live is None:
        sealed = read_evidence(payload)
        d1_judgment = judge_claim(fixture.claim, sealed, fixture.d1_bundle)
    else:
        sealed, d1_judgment = run_live_d1(
            fixture.claim,
            fixture.d1_bundle,
            payload,
            live,
            client=client,
        )
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
        report_verdict=_report_verdict(
            fixture,
            audit,
            reconciliation,
            card,
            live=live,
            d1_status=d1_judgment.execution_status,
        ),
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
    *,
    live: LoadedLive | None = None,
    d1_status: ExecutionStatus | None = None,
) -> ReportVerdict:
    if live is None:
        inference = _OFFLINE_LIMITATION
    else:
        inference = (
            f"This fixture run called model {live.model_id} at {live.base_url} "
            "for the evidence reader and the claim-visible judge. "
            "Citation audit and reconciliation stayed on the deterministic rules."
        )
    limitations = [
        "Labels describe the supplied evidence collection only, not an unrestricted scientific conclusion.",
        inference,
        "Numerical calibration is unvalidated. Raw scores and calibrated probabilities are null.",
    ]
    if live is not None and d1_status is not ExecutionStatus.COMPLETED:
        limitations.append(
            "The live model response was not accepted. The D1 label is the fail-closed "
            "placeholder unaddressed, and execution_status carries the failure. "
            "The model text was not turned into a scientific label."
        )
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
        description=(
            "Run the staged judgment pipeline on one fixture claim and emit Verdict JSON. "
            "The default is offline and deterministic. "
            f"--live calls an OpenAI-compatible server. Default base_url is {DEFAULT_BASE_URL} "
            f"(LM Studio on this machine). Default model_id is {DEFAULT_MODEL_ID}. "
            "RFC1918 hosts such as http://192.168.1.10:1234/v1 are allowed. "
            "Public hosts are refused. pytest does not pass --live."
        )
    )
    parser.add_argument("--fixture", type=Path, required=True, help="One fixture claim JSON file.")
    parser.add_argument(
        "--output",
        type=Path,
        help="Write Verdict JSON here. Omit to write it to stdout.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Call the local OpenAI-compatible endpoint for the evidence reader and the "
            f"claim-visible judge. Default base_url {DEFAULT_BASE_URL}. "
            f"Default model_id {DEFAULT_MODEL_ID}. "
            "Also allowed: http://192.168.1.10:1234/v1 and other RFC1918 hosts. "
            "Loopback names are 127.0.0.1 and localhost. "
            "An unparsable response is written with execution_status failed and the process exits 1. "
            "The offline fixture path does not use this flag."
        ),
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help=(
            "Judgment live YAML, used only with --live. "
            "Default is configs/judgment/fixture_live.yaml, which sets "
            f"base_url {DEFAULT_BASE_URL} and model_id {DEFAULT_MODEL_ID}."
        ),
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help=(
            "Override base_url for --live. Loopback or RFC1918 only. "
            f"Default {DEFAULT_BASE_URL}. Example private-LAN host: http://192.168.1.10:1234/v1."
        ),
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help=f"Override model_id for --live. Default {DEFAULT_MODEL_ID}.",
    )
    args = parser.parse_args(argv)
    if not args.live and (args.config is not None or args.base_url is not None or args.model_id is not None):
        parser.error("--config, --base-url, and --model-id are only used with --live")
    fixture = load_fixture(args.fixture)
    live = None
    if args.live:
        root = find_repo_root()
        config_path = default_live_config(root) if args.config is None else _resolve(root, args.config)
        try:
            live = load_live_settings(
                config_path,
                base_url=args.base_url,
                model_id=args.model_id,
                root=root,
            )
        except (EndpointPolicyError, LiveConfigError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
    verdict = run_fixture(fixture, live=live)
    text = verdict.model_dump_json(indent=2) + "\n"
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    if live is not None:
        d1 = next(item for item in verdict.judgments if item.evidence_scope is EvidenceScope.D1)
        if d1.execution_status is not ExecutionStatus.COMPLETED:
            return 1
    return 0


def _resolve(root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return root / value


if __name__ == "__main__":
    raise SystemExit(main())
