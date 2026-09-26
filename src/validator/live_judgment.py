"""Optional live reader and claim-visible judge for one fixture claim.

Importing this module does not open a socket. The offline fixture path does
not call ``run_live_d1``. ``--live`` loads ``configs/judgment/fixture_live.yaml``:

    base_url: http://127.0.0.1:1234/v1
    model_id: qwen2.5-coder-1.5b-instruct

An RFC1918 URL such as ``http://192.168.1.10:1234/v1`` is allowed. Public
hosts are refused. The reader request is the neutral question and D1 passage
text only. ``asserted_answer`` is not a reader field and is not sent to the
judge model either.

A response that is not the expected JSON is fail-closed. The D1 judgment
then uses the placeholder label ``unaddressed`` and ``execution_status``
``failed`` or ``timeout``. That placeholder is not read off the model text.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from validator.citation_auditor import (
    CitationAudit,
    CitationFlag,
    assert_d0_boundary,
    failed_audit,
    structural_defect,
)
from validator.evidence_reader import (
    IsolationError,
    SealedEvidenceRecord,
    assert_reader_boundary,
    shuffle_passages,
)
from validator.inference_client import (
    EndpointPolicyError,
    InferenceTransportError,
    LocalChatClient,
)
from validator.judge import assert_judge_boundary
from validator.label_policy import PassageView, evidence_span_id
from validator.retrieval.models import EvidenceBundle
from validator.same_evidence._repo import find_repo_root
from validator.same_evidence.b2 import BaselineDataError, LabelError, assert_local_or_private, extract_json_object
from validator.schemas import (
    Claim,
    Evidence,
    EvidenceScope,
    ExecutionStatus,
    GoldProvenance,
    Judgment,
    LabelSpace,
    ScientificLabel,
)

_READER_FAILURE_ANSWER = (
    "Live evidence reader failed closed. No evidence-only answer was accepted."
)
_FOUR_WAY = {item.value for item in ScientificLabel}
_CITATION_ADEQUACY = {"adequate", "inadequate", "unverifiable"}


class LiveConfigError(RuntimeError):
    """The live YAML or a prompt file cannot be used."""


class LiveParseError(ValueError):
    """Model text was not a reader or judge object this slice can accept."""


class _PromptPaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reader: str = Field(min_length=1)
    judge: str = Field(min_length=1)
    citation_auditor: str = Field(min_length=1)


class _LiveFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str = Field(min_length=1)
    base_url: str = Field(min_length=1)
    temperature: float
    timeout_seconds: float = Field(gt=0)
    prompts: _PromptPaths


@dataclass(frozen=True)
class LoadedLive:
    """One local endpoint and the two judgment prompts."""

    model_id: str
    base_url: str
    temperature: float
    timeout_seconds: float
    reader_prompt: str
    judge_prompt: str
    citation_auditor_prompt: str


class ChatClient(Protocol):
    """The only method the live path needs. Tests supply a fake."""

    def complete(self, system_prompt: str, payload: dict) -> str:
        """Return one assistant message."""


def default_live_config(root: Path | None = None) -> Path:
    """Committed live config. Relative paths inside it are from the repo root."""
    checkout = root if root is not None else find_repo_root()
    return checkout / "configs" / "judgment" / "fixture_live.yaml"


def load_live_settings(
    path: Path,
    *,
    base_url: str | None = None,
    model_id: str | None = None,
    temperature: float | None = None,
    timeout_seconds: float | None = None,
    root: Path | None = None,
) -> LoadedLive:
    """Load the live YAML and refuse a public ``base_url`` before any request."""
    checkout = root if root is not None else find_repo_root()
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise LiveConfigError(f"{path} is not a YAML mapping")
    if base_url is not None:
        raw["base_url"] = base_url
    if model_id is not None:
        raw["model_id"] = model_id
    if temperature is not None:
        raw["temperature"] = temperature
    if timeout_seconds is not None:
        raw["timeout_seconds"] = timeout_seconds
    try:
        parsed = _LiveFile.model_validate(raw)
    except ValidationError as exc:
        raise LiveConfigError(f"invalid judgment live config {path}: {exc}") from exc
    try:
        assert_local_or_private(parsed.base_url)
    except BaselineDataError as exc:
        raise EndpointPolicyError(str(exc)) from exc
    reader_prompt = _read_prompt(checkout, parsed.prompts.reader)
    judge_prompt = _read_prompt(checkout, parsed.prompts.judge)
    citation_auditor_prompt = _read_prompt(checkout, parsed.prompts.citation_auditor)
    return LoadedLive(
        model_id=parsed.model_id,
        base_url=parsed.base_url,
        temperature=parsed.temperature,
        timeout_seconds=parsed.timeout_seconds,
        reader_prompt=reader_prompt,
        judge_prompt=judge_prompt,
        citation_auditor_prompt=citation_auditor_prompt,
    )


def isolated_reader_request(payload: dict) -> dict:
    """Shuffle D1 passages and return the only object the live reader may see."""
    parsed = assert_reader_boundary(payload)
    shuffled = shuffle_passages(parsed.passages, parsed.neutral_question)
    request = {
        "neutral_question": parsed.neutral_question,
        "passages": [
            {"span_id": passage.span_id, "doc_id": passage.doc_id, "text": passage.text}
            for passage in shuffled
        ],
    }
    assert_reader_boundary(request)
    return request


def run_live_d1(
    claim: Claim,
    bundle: EvidenceBundle,
    reader_payload: dict,
    live: LoadedLive,
    *,
    client: ChatClient | None = None,
) -> tuple[SealedEvidenceRecord, Judgment]:
    """Call the reader, then the judge. Parse failures stay fail-closed."""
    chat = client if client is not None else _client_for(live)
    request = isolated_reader_request(reader_payload)
    try:
        raw = chat.complete(live.reader_prompt, request)
        answer, cited = _parse_reader(raw, {passage["span_id"] for passage in request["passages"]})
    except LiveParseError:
        return _failed_reader_record(claim), _failed_judgment(
            claim.claim_id,
            status=ExecutionStatus.FAILED,
            reason="live_parse_failed",
        )
    except InferenceTransportError as exc:
        return _failed_reader_record(claim), _failed_judgment(
            claim.claim_id,
            status=_status_for_transport(exc),
            reason=_reason_for_transport(exc),
        )
    sealed = SealedEvidenceRecord.from_body(
        neutral_question=request["neutral_question"],
        answer=answer,
        cited_span_ids=cited,
    )
    views = assert_judge_boundary(claim, sealed, bundle)
    judge_request = _judge_request(claim, sealed, bundle, views)
    try:
        raw = chat.complete(live.judge_prompt, judge_request)
        parsed = _parse_judge(raw, {view.span_id for view in views})
    except LiveParseError:
        return sealed, _failed_judgment(
            claim.claim_id,
            status=ExecutionStatus.FAILED,
            reason="live_parse_failed",
        )
    except InferenceTransportError as exc:
        return sealed, _failed_judgment(
            claim.claim_id,
            status=_status_for_transport(exc),
            reason=_reason_for_transport(exc),
        )
    return sealed, Judgment(
        claim_id=claim.claim_id,
        evidence_scope=EvidenceScope.D1,
        label_space=LabelSpace.MAVS_FOUR_WAY,
        label=parsed["label"],
        rationale_codes=parsed["rationale_codes"],
        cited_span_ids=parsed["cited_span_ids"],
        raw_scores=None,
        calibrated_probabilities=None,
        execution_status=ExecutionStatus.COMPLETED,
        uncertainty_reasons=parsed["uncertainty_reasons"],
        gold_provenance=GoldProvenance.NONE,
    )


def run_live_d0(
    claim: Claim,
    d0_evidence: list[Evidence],
    live: LoadedLive,
    *,
    client: ChatClient | None = None,
) -> CitationAudit:
    """Audit the original citations with the same model that judges D1.

    The D1 arm is model-based, so a rule-based D0 arm would make almost every
    reconciliation a mechanism artifact instead of an evidence disagreement.
    D0 stays claim-visible and never sees D1. Parse and transport failures are
    fail-closed: the label is a schema token, never model text.
    """
    assert_d0_boundary(d0_evidence)
    if not d0_evidence:
        return failed_audit(claim, reason="missing_required_citation")

    views: list[PassageView] = []
    by_span: dict[str, Evidence] = {}
    flags: list[CitationFlag] = []
    structural_failure = False
    for evidence in d0_evidence:
        view, defect = structural_defect(claim, evidence)
        if view is None:
            structural_failure = True
            flags.append(defect)
            continue
        views.append(view)
        by_span[view.span_id] = evidence

    if not views:
        return failed_audit(claim, reason="missing_required_citation", flags=flags)

    chat = client if client is not None else _client_for(live)
    request = _citation_request(claim, d0_evidence, views)
    try:
        raw = chat.complete(live.citation_auditor_prompt, request)
        parsed = _parse_citation_audit(raw, {view.span_id for view in views})
    except LiveParseError:
        return failed_audit(claim, reason="live_parse_failed", flags=flags or None)
    except InferenceTransportError as exc:
        return failed_audit(claim, reason=_reason_for_transport(exc), flags=flags or None)

    rated = parsed["citations"]
    for view in views:
        evidence = by_span[view.span_id]
        entry = rated.get(view.span_id)
        flags.append(
            CitationFlag(
                claim_id=claim.claim_id,
                span_id=view.span_id,
                doc_id=evidence.doc_id,
                adequacy=entry["adequacy"] if entry else "unverifiable",
                defects=list(entry["defects"]) if entry else ["citation_not_rated"],
            )
        )

    return CitationAudit(
        judgment=Judgment(
            claim_id=claim.claim_id,
            evidence_scope=EvidenceScope.D0,
            label_space=LabelSpace.MAVS_FOUR_WAY,
            label=parsed["label"],
            rationale_codes=parsed["rationale_codes"],
            cited_span_ids=parsed["cited_span_ids"],
            raw_scores=None,
            calibrated_probabilities=None,
            execution_status=(
                ExecutionStatus.FAILED if structural_failure else ExecutionStatus.COMPLETED
            ),
            uncertainty_reasons=parsed["uncertainty_reasons"],
            gold_provenance=GoldProvenance.NONE,
        ),
        flags=flags,
    )


def _citation_request(
    claim: Claim, d0_evidence: list[Evidence], views: list[PassageView]
) -> dict:
    """Claim plus original citations. No D1, no sealed reader, no asserted answer."""
    by_span = {}
    for evidence in d0_evidence:
        span = evidence_span_id(evidence)
        if span is not None:
            by_span[span] = evidence
    passages = [
        {
            "span_id": view.span_id,
            "doc_id": by_span[view.span_id].doc_id,
            "text": view.text,
        }
        for view in views
    ]
    request = {
        "claim_id": claim.claim_id,
        "normalized_claim": claim.normalized_claim,
        "passages": passages,
    }
    if _has_key(request, "asserted_answer"):
        raise IsolationError("citation audit request contains asserted_answer")
    return request


def _parse_citation_audit(text: str, allowed_span_ids: set[str]) -> dict:
    """Reuse the judge contract and add per-citation adequacy ratings."""
    parsed = _parse_judge(text, allowed_span_ids)
    raw = _json_object(text)
    entries = raw.get("citations", [])
    if not isinstance(entries, list):
        raise LiveParseError("citation audit citations must be a list")
    rated: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise LiveParseError("citation audit citations must be a list of objects")
        span = entry.get("span_id")
        if not isinstance(span, str) or span not in allowed_span_ids:
            raise LiveParseError("citation audit rated a span id that was not supplied")
        adequacy = entry.get("adequacy")
        if adequacy not in _CITATION_ADEQUACY:
            raise LiveParseError("citation audit adequacy is outside the allowed set")
        defects = entry.get("defects", [])
        if not isinstance(defects, list) or any(not isinstance(item, str) for item in defects):
            raise LiveParseError("citation audit defects must be a list of strings")
        rated[span] = {
            "adequacy": adequacy,
            "defects": [item.strip() for item in defects if item.strip()],
        }
    parsed["citations"] = rated
    return parsed


def _client_for(live: LoadedLive) -> LocalChatClient:
    return LocalChatClient(
        base_url=live.base_url,
        model_id=live.model_id,
        temperature=live.temperature,
        timeout_seconds=live.timeout_seconds,
    )


def _read_prompt(root: Path, value: str) -> str:
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        raise LiveConfigError(f"prompt file is missing: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise LiveConfigError(f"prompt file is empty: {path}")
    return text


def _parse_reader(text: str, allowed_span_ids: set[str]) -> tuple[str, list[str]]:
    parsed = _json_object(text)
    answer = parsed.get("answer")
    cited = parsed.get("cited_span_ids")
    if not isinstance(answer, str) or not answer.strip():
        raise LiveParseError("reader response is missing answer text")
    if not isinstance(cited, list) or any(not isinstance(item, str) or not item for item in cited):
        raise LiveParseError("reader response cited_span_ids must be a list of span ids")
    if any(item not in allowed_span_ids for item in cited):
        raise LiveParseError("reader cited span ids that were not in the evidence payload")
    return answer.strip(), list(cited)


def _parse_judge(text: str, allowed_span_ids: set[str]) -> dict:
    parsed = _json_object(text)
    raw_label = parsed.get("label")
    if not isinstance(raw_label, str):
        raise LiveParseError("judge response label was not a string")
    label = raw_label.strip().lower()
    if label not in _FOUR_WAY:
        raise LiveParseError("judge response label is outside the four-way set")
    cited = parsed.get("cited_span_ids")
    if not isinstance(cited, list) or any(not isinstance(item, str) for item in cited):
        raise LiveParseError("judge response cited_span_ids must be a list of strings")
    if any(item not in allowed_span_ids for item in cited):
        raise LiveParseError("judge cited span ids that were not in the evidence collection")
    codes = parsed.get("rationale_codes", [])
    if not isinstance(codes, list) or any(not isinstance(item, str) or not item.strip() for item in codes):
        raise LiveParseError("judge response rationale_codes must be a list of strings")
    reasons = parsed.get("uncertainty_reasons", [])
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise LiveParseError("judge response uncertainty_reasons must be a list of strings")
    return {
        "label": label,
        "rationale_codes": [item.strip() for item in codes] or ["live_model"],
        "cited_span_ids": list(cited),
        "uncertainty_reasons": [item.strip() for item in reasons if item.strip()],
    }


def _json_object(text: str) -> dict:
    try:
        return extract_json_object(text)
    except LabelError as exc:
        raise LiveParseError(str(exc)) from exc


def _judge_request(
    claim: Claim,
    sealed: SealedEvidenceRecord,
    bundle: EvidenceBundle,
    views: list[PassageView],
) -> dict:
    passages = []
    for passage, view in zip(bundle.passages, views, strict=True):
        span = evidence_span_id(passage)
        if span != view.span_id:
            raise IsolationError("judge passage order does not match the sealed bundle")
        passages.append({"span_id": view.span_id, "doc_id": passage.doc_id, "text": view.text})
    request = {
        "claim_id": claim.claim_id,
        "normalized_claim": claim.normalized_claim,
        "neutral_question": sealed.neutral_question,
        "sealed_reader": {
            "answer": sealed.answer,
            "cited_span_ids": list(sealed.cited_span_ids),
        },
        "passages": passages,
    }
    if _has_key(request, "asserted_answer"):
        raise IsolationError("judge request contains asserted_answer")
    return request


def _has_key(value: object, key: str) -> bool:
    if isinstance(value, dict):
        return any(child == key or _has_key(item, key) for child, item in value.items())
    if isinstance(value, list):
        return any(_has_key(item, key) for item in value)
    return False


def _failed_reader_record(claim: Claim) -> SealedEvidenceRecord:
    if claim.neutral_question is None or not claim.neutral_question.strip():
        raise IsolationError("live reader failure record requires neutral_question")
    return SealedEvidenceRecord.from_body(
        neutral_question=claim.neutral_question,
        answer=_READER_FAILURE_ANSWER,
        cited_span_ids=[],
    )


def _failed_judgment(claim_id: str, *, status: ExecutionStatus, reason: str) -> Judgment:
    """Placeholder ``unaddressed`` plus a failed execution status.

    The label is the schema's fail-closed token. It is not parsed from the
    model response, and the model response is not stored on the judgment.
    """
    return Judgment(
        claim_id=claim_id,
        evidence_scope=EvidenceScope.D1,
        label_space=LabelSpace.MAVS_FOUR_WAY,
        label=ScientificLabel.UNADDRESSED.value,
        rationale_codes=[reason],
        cited_span_ids=[],
        raw_scores=None,
        calibrated_probabilities=None,
        execution_status=status,
        uncertainty_reasons=[reason],
        gold_provenance=GoldProvenance.NONE,
    )


def _status_for_transport(exc: InferenceTransportError) -> ExecutionStatus:
    if exc.timed_out:
        return ExecutionStatus.TIMEOUT
    return ExecutionStatus.FAILED


def _reason_for_transport(exc: InferenceTransportError) -> str:
    if exc.timed_out:
        return "live_timeout"
    return "live_endpoint_unavailable"


__all__ = [
    "EndpointPolicyError",
    "LoadedLive",
    "LiveConfigError",
    "default_live_config",
    "isolated_reader_request",
    "load_live_settings",
    "run_live_d0",
    "run_live_d1",
]
