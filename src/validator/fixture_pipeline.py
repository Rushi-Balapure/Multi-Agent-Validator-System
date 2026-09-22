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

A report fixture runs the same stages for every kept claim. It starts from
``decompose`` or from fixture claims, then uses a fixture EvidenceBundle.
The default is ``dry_run``: no index and no model. Opt-in gather lives in
``python -m validator.runner --gather`` and is not the pytest path.

    PYTHONPATH=src python3 -m validator.fixture_pipeline \\
        --fixture tests/fixtures/judgment/e2e_happy.json --dry-run \\
        --output artifacts/judgment/e2e_happy_verdict.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from validator.citation_auditor import CitationAudit, CitationFlag, audit_citations
from validator.decompose import CLAIM_BUDGET, DecomposeInput, decompose
from validator.evidence_reader import (
    IsolationError,
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
from validator.retrieval.models import PASSAGE_CEILING, EvidenceBundle
from validator.same_evidence._repo import find_repo_root
from validator.schemas import (
    Claim,
    Evidence,
    EvidenceScope,
    ExecutionStatus,
    GoldProvenance,
    Judgment,
    LabelSpace,
    ReportVerdict,
    ScientificLabel,
)

_OFFLINE_LIMITATION = (
    "This fixture run uses deterministic lexical rules. "
    "Live model prompts are a later slice and were not called."
)
_PROJECT_CLAIM_ID = r"^scifact:\d+$"
JUDGE_PASSAGE_BUDGET = PASSAGE_CEILING


class PipelineError(ValueError):
    """The staged report could not be assembled from its fixture."""


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


def cap_evidence_bundle(bundle: EvidenceBundle, limit: int = JUDGE_PASSAGE_BUDGET) -> EvidenceBundle:
    """Keep at most ``limit`` passages for the reader and the judge.

    The research-plan development default is 8, which is also the bundle
    ceiling. A shorter limit is only for tests of the cap. Truncation keeps
    the highest-ranked prefix and rewrites ranks to 1..n.
    """
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise PipelineError("passage budget must be an integer")
    if limit < 1 or limit > PASSAGE_CEILING:
        raise PipelineError(f"passage budget must be from 1 to {PASSAGE_CEILING}")
    if len(bundle.passages) <= limit:
        return bundle
    passages = [
        passage.model_copy(update={"rank": rank})
        for rank, passage in enumerate(bundle.passages[:limit], start=1)
    ]
    return bundle.model_copy(update={"passages": passages})


def run_fixture(
    fixture: JudgmentFixture,
    *,
    live: LoadedLive | None = None,
    client: Any = None,
    passage_budget: int = JUDGE_PASSAGE_BUDGET,
) -> StagedVerdict:
    """Run the five stages. The claim is not an argument to the reader.

    ``live`` is omitted for the offline path. A client is only used with
    ``live``; tests pass a fake so the default path never opens a socket.
    ``passage_budget`` caps the D1 passages the reader and the judge see.
    """
    bundle = cap_evidence_bundle(fixture.d1_bundle, passage_budget)
    if bundle is not fixture.d1_bundle:
        fixture = fixture.model_copy(update={"d1_bundle": bundle})
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


class ClaimAttachment(BaseModel):
    """D0 citations and an optional fixture D1 bundle for one atomic claim.

    ``retrieval_claim_id`` is the project id (``scifact:N``) consumed by
    EvidenceBundle. The proposer may use a different id; the verdict keeps
    that id beside the retrieval id.
    """

    model_config = ConfigDict(extra="forbid")

    retrieval_claim_id: str = Field(pattern=_PROJECT_CLAIM_ID)
    d0_evidence: list[Evidence]
    d1_bundle: EvidenceBundle | None = None

    @model_validator(mode="after")
    def bundle_matches_retrieval_id(self) -> ClaimAttachment:
        if self.d1_bundle is not None and self.d1_bundle.claim_id != self.retrieval_claim_id:
            raise ValueError("fixture D1 bundle claim_id must match retrieval_claim_id")
        return self


class ReportJudgmentFixture(BaseModel):
    """One report: decompose a frozen conclusion, or start from fixture claims.

    Exactly one of ``decompose`` or ``claims`` is set. ``attachments`` lines
    up with the claims that will be judged, in order. Decompose already drops
    claims past its budget, so attachments cover the kept claims only.
    """

    model_config = ConfigDict(extra="forbid")

    fixture_id: str = Field(min_length=1)
    dry_run: bool = True
    decompose: DecomposeInput | None = None
    claims: list[Claim] = Field(default_factory=list)
    attachments: list[ClaimAttachment] = Field(min_length=1)

    @model_validator(mode="after")
    def one_claim_source(self) -> ReportJudgmentFixture:
        has_decompose = self.decompose is not None
        has_claims = bool(self.claims)
        if has_decompose == has_claims:
            raise ValueError("provide exactly one of decompose or claims")
        return self


class ClaimE2EVerdict(BaseModel):
    """One claim with separate D0, D1, and reconciled D0∪D1 judgments."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str
    proposer_claim_id: str | None = None
    d0: Judgment
    d1: Judgment
    reconciled: Judgment
    citation_flags: list[CitationFlag]
    reconciler_notes: list[ReconcilerNote]
    claim_card: ClaimCard
    sealed_reader: SealedEvidenceRecord


class ReportE2EVerdict(BaseModel):
    """Report-level verdict. D0 labels stay on ``d0`` and are not replaced."""

    model_config = ConfigDict(extra="forbid")

    fixture_id: str
    report_id: str | None = None
    dry_run: bool
    partial: bool
    unchecked_spans: list[str]
    claims_in_report: int
    claims_judged: int
    claims: list[ClaimE2EVerdict]
    report_verdict: ReportVerdict


def load_report_fixture(path: Path) -> ReportJudgmentFixture:
    return ReportJudgmentFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))


def reconciled_judgment(d0: Judgment, d1: Judgment) -> Judgment:
    """What can be said after reconciliation, without replacing ``d0``.

    Agreement copies the shared label onto a ``D0_union_D1`` judgment.
    Disagreement or a failed D0 audit is underdetermined. The D1 label is
    not written onto the D0 judgment, and D1 is not used to repair D0.
    """
    if d0.claim_id != d1.claim_id:
        raise PipelineError("D0 and D1 judgments are for different claims")
    if d0.evidence_scope is not EvidenceScope.D0 or d1.evidence_scope is not EvidenceScope.D1:
        raise PipelineError("reconciled view expects one D0 judgment and one D1 judgment")
    both_completed = (
        d0.execution_status is ExecutionStatus.COMPLETED
        and d1.execution_status is ExecutionStatus.COMPLETED
    )
    if both_completed and d0.label == d1.label:
        label = d0.label
        codes = ["labels_agree"]
        status = ExecutionStatus.COMPLETED
        uncertainty: list[str] = []
    else:
        label = ScientificLabel.UNDERDETERMINED.value
        codes = ["d0_d1_conflict"]
        if d0.execution_status is not ExecutionStatus.COMPLETED:
            codes.append("d0_not_repaired_from_d1")
        status = ExecutionStatus.COMPLETED if both_completed else ExecutionStatus.FAILED
        uncertainty = ["d0_d1_disagreement"]
    cited: list[str] = []
    for span_id in [*d0.cited_span_ids, *d1.cited_span_ids]:
        if span_id not in cited:
            cited.append(span_id)
    return Judgment(
        claim_id=d0.claim_id,
        evidence_scope=EvidenceScope.D0_UNION_D1,
        label_space=LabelSpace.MAVS_FOUR_WAY,
        label=label,
        rationale_codes=codes,
        cited_span_ids=cited,
        raw_scores=None,
        calibrated_probabilities=None,
        execution_status=status,
        uncertainty_reasons=uncertainty,
        gold_provenance=GoldProvenance.NONE,
    )


def resolve_d1_bundle(
    claim: Claim,
    attachment: ClaimAttachment,
    *,
    gather_fn: Callable[[Claim], EvidenceBundle] | None,
    dry_run: bool,
    passage_budget: int,
) -> EvidenceBundle:
    """Use the fixture bundle. Call ``gather_fn`` only when dry_run is off."""
    if attachment.d1_bundle is not None:
        bundle = attachment.d1_bundle
    elif dry_run:
        raise PipelineError(
            f"{claim.claim_id} has no fixture D1 bundle. "
            "dry_run does not call gather. "
            "Opt in with python -m validator.runner --gather."
        )
    elif gather_fn is None:
        raise PipelineError(f"{claim.claim_id} has no fixture D1 bundle and no gather function")
    else:
        bundle = gather_fn(claim)
        if not isinstance(bundle, EvidenceBundle):
            raise PipelineError("gather must return an EvidenceBundle")
        if bundle.claim_id != claim.claim_id:
            raise PipelineError("gather bundle claim_id does not match the claim")
    return cap_evidence_bundle(bundle, passage_budget)


def run_report(
    fixture: ReportJudgmentFixture,
    *,
    gather_fn: Callable[[Claim], EvidenceBundle] | None = None,
    dry_run: bool | None = None,
    claim_budget: int = CLAIM_BUDGET,
    passage_budget: int = JUDGE_PASSAGE_BUDGET,
) -> ReportE2EVerdict:
    """Decompose or take fixture claims, then run staged judgment for each.

    The reader never receives the claim. The auditor receives D0 only.
    ``dry_run`` defaults to the fixture flag. A fixture marked ``dry_run``
    refuses an explicit live gather request.
    """
    if isinstance(claim_budget, bool) or not isinstance(claim_budget, int):
        raise PipelineError("claim budget must be an integer")
    if claim_budget < 1 or claim_budget > CLAIM_BUDGET:
        raise PipelineError(f"claim budget must be from 1 to {CLAIM_BUDGET}")
    offline = fixture.dry_run if dry_run is None else dry_run
    if fixture.dry_run and dry_run is False:
        raise PipelineError("this fixture is marked dry_run and refuses live gather")

    raw_claims, unchecked, report_id = _claims_for_report(fixture, claim_budget)
    if len(fixture.attachments) != len(raw_claims):
        raise PipelineError(
            f"attachments ({len(fixture.attachments)}) must match "
            f"claims to judge ({len(raw_claims)})"
        )
    claims_in_report = len(raw_claims) + len(unchecked)
    if len(raw_claims) > claim_budget:
        for claim in raw_claims[claim_budget:]:
            span = claim.exact_source_span or claim.normalized_claim
            if span not in unchecked:
                unchecked.append(span)
        raw_claims = raw_claims[:claim_budget]
        attachments = fixture.attachments[:claim_budget]
    else:
        attachments = list(fixture.attachments)
    retrieval_ids = [item.retrieval_claim_id for item in attachments]
    if len(retrieval_ids) != len(set(retrieval_ids)):
        raise PipelineError("retrieval_claim_id values must be unique in one report")

    id_map = {
        claim.claim_id: attachment.retrieval_claim_id
        for claim, attachment in zip(raw_claims, attachments, strict=True)
    }
    claim_verdicts: list[ClaimE2EVerdict] = []
    gathered = False
    centrals: list[Any] = []
    links: list[Any] = []
    conflicts: list[Any] = []
    cards: list[str] = []
    for claim, attachment in zip(raw_claims, attachments, strict=True):
        bound, proposer_id = _bind_claim(claim, attachment.retrieval_claim_id, id_map)
        bundle = resolve_d1_bundle(
            bound,
            attachment,
            gather_fn=gather_fn,
            dry_run=offline,
            passage_budget=passage_budget,
        )
        if attachment.d1_bundle is None:
            gathered = True
        staged = run_fixture(
            JudgmentFixture(
                fixture_id=f"{fixture.fixture_id}:{bound.claim_id}",
                claim=bound,
                d0_evidence=list(attachment.d0_evidence),
                d1_bundle=bundle,
            ),
            passage_budget=passage_budget,
        )
        by_scope = {item.evidence_scope: item for item in staged.judgments}
        d0 = by_scope[EvidenceScope.D0]
        d1 = by_scope[EvidenceScope.D1]
        union = reconciled_judgment(d0, d1)
        claim_verdicts.append(
            ClaimE2EVerdict(
                claim_id=bound.claim_id,
                proposer_claim_id=proposer_id,
                d0=d0,
                d1=d1,
                reconciled=union,
                citation_flags=staged.citation_flags,
                reconciler_notes=staged.reconciler_notes,
                claim_card=staged.claim_card,
                sealed_reader=staged.sealed_reader,
            )
        )
        centrals.extend(staged.report_verdict.central_claim_outcomes)
        links.extend(staged.report_verdict.inference_link_status)
        conflicts.extend(staged.report_verdict.conflicts_d0_d1)
        cards.append(staged.claim_card.display_text)

    partial = bool(unchecked)
    return ReportE2EVerdict(
        fixture_id=fixture.fixture_id,
        report_id=report_id,
        dry_run=offline,
        partial=partial,
        unchecked_spans=list(unchecked),
        claims_in_report=claims_in_report,
        claims_judged=len(claim_verdicts),
        claims=claim_verdicts,
        report_verdict=_report_level_verdict(
            claim_verdicts,
            centrals,
            links,
            conflicts,
            cards,
            unchecked=unchecked,
            claims_in_report=claims_in_report,
            offline=offline,
            gathered=gathered,
        ),
    )


def _claims_for_report(
    fixture: ReportJudgmentFixture,
    claim_budget: int,
) -> tuple[list[Claim], list[str], str | None]:
    if fixture.decompose is not None:
        result = decompose(fixture.decompose, dry_run=True, claim_budget=claim_budget)
        return list(result.claims), list(result.unchecked_spans), result.report_id
    report_id = fixture.claims[0].report_id if fixture.claims else None
    return list(fixture.claims), [], report_id


def _bind_claim(
    claim: Claim,
    retrieval_claim_id: str,
    id_map: dict[str, str],
) -> tuple[Claim, str | None]:
    proposer = None if claim.claim_id == retrieval_claim_id else claim.claim_id
    dependencies = [id_map.get(dep, dep) for dep in claim.dependencies]
    bound = claim.model_copy(
        update={"claim_id": retrieval_claim_id, "dependencies": dependencies}
    )
    return bound, proposer


def _report_level_verdict(
    claim_verdicts: list[ClaimE2EVerdict],
    centrals: list[Any],
    links: list[Any],
    conflicts: list[Any],
    cards: list[str],
    *,
    unchecked: list[str],
    claims_in_report: int,
    offline: bool,
    gathered: bool,
) -> ReportVerdict:
    if gathered:
        inference = (
            "D1 bundles without a fixture passage set were loaded by the opt-in gather path. "
            "The reader, judge, citation audit, and reconciler stayed on the deterministic rules."
        )
    elif offline:
        inference = _OFFLINE_LIMITATION
    else:
        inference = (
            "Gather was allowed. Every judged claim already had a fixture D1 bundle, "
            "so gather was not called. "
            "The reader, judge, citation audit, and reconciler stayed on the deterministic rules."
        )
    limitations = [
        "Labels describe the supplied evidence collection only, not an unrestricted scientific conclusion.",
        inference,
        "Numerical calibration is unvalidated. Raw scores and calibrated probabilities are null.",
        "D0 citation faithfulness is not repaired or replaced with D1 evidence.",
    ]
    if unchecked:
        limitations.append(
            "The claim budget was exceeded. Unchecked spans are listed in claim_coverage "
            "and were not given a scientific label."
        )
    if any(item.d0.execution_status is not ExecutionStatus.COMPLETED for item in claim_verdicts):
        limitations.append(
            "The citation audit failed closed for at least one claim. "
            "D1 was not used to repair D0 faithfulness."
        )
    return ReportVerdict(
        claim_coverage={
            "claims_in_report": claims_in_report,
            "claims_judged": len(claim_verdicts),
            "partial": bool(unchecked),
            "unchecked_spans": list(unchecked),
            "claim_ids": [item.claim_id for item in claim_verdicts],
        },
        central_claim_outcomes=centrals,
        inference_link_status=links,
        conflicts_d0_d1=conflicts,
        display_explanation="\n\n".join(cards),
        limitations=limitations,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the staged judgment pipeline and emit Verdict JSON. "
            "The default is offline and deterministic. "
            "A report fixture (decompose or fixture claims, then D0 and D1) "
            "writes D0, D1, and reconciled D0 union D1 views. "
            f"--live calls an OpenAI-compatible server for a single claim fixture. "
            f"Default base_url is {DEFAULT_BASE_URL} "
            f"(LM Studio on this machine). Default model_id is {DEFAULT_MODEL_ID}. "
            "RFC1918 hosts such as http://192.168.1.10:1234/v1 are allowed. "
            "Public hosts are refused. pytest does not pass --live."
        )
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        required=True,
        help="A single-claim fixture or a report fixture JSON file.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Write Verdict JSON here. Omit to write it to stdout.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Offline fixture path. This is the default. "
            "Report fixtures use fixture D1 bundles and do not call gather or a model. "
            "Do not combine with --live."
        ),
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
    if args.dry_run and args.live:
        parser.error("--dry-run cannot be combined with --live")
    if not args.live and (args.config is not None or args.base_url is not None or args.model_id is not None):
        parser.error("--config, --base-url, and --model-id are only used with --live")
    payload = json.loads(args.fixture.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "attachments" in payload:
        if args.live:
            parser.error("--live applies to a single claim fixture, not a report fixture")
        try:
            report = ReportJudgmentFixture.model_validate(payload)
            report_verdict = run_report(report, dry_run=True)
        except (PipelineError, IsolationError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        _write_output(args.output, report_verdict.model_dump_json(indent=2) + "\n")
        return 0
    fixture = JudgmentFixture.model_validate(payload)
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
    _write_output(args.output, verdict.model_dump_json(indent=2) + "\n")
    if live is not None:
        d1 = next(item for item in verdict.judgments if item.evidence_scope is EvidenceScope.D1)
        if d1.execution_status is not ExecutionStatus.COMPLETED:
            return 1
    return 0


def _write_output(path: Path | None, text: str) -> None:
    if path is None:
        sys.stdout.write(text)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _resolve(root: Path, value: Path) -> Path:
    if value.is_absolute():
        return value
    return root / value


if __name__ == "__main__":
    raise SystemExit(main())
