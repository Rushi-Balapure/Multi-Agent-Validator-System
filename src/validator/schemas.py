"""Section-4 records for a validator run.

The research plan names five records: Run, Claim, Evidence, Judgment, and
ReportVerdict. Field names follow that section and the JSON schemas in
``schemas/``.

Execution status is a control field (completed, failed, timeout). It is not a
scientific label. The four project labels are Supported, Contradicted,
Unaddressed, and Underdetermined, stored as the lowercase tokens in
``mavs_evidence_label.schema.json``. Native SciFact gold is only ``SUPPORT``
or ``CONTRADICT``. Empty SciFact evidence is not a four-way label.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_SHA256 = r"^[a-f0-9]{64}$"


class ExecutionStatus(str, Enum):
    """How a run or judgment finished. Never an evidence verdict."""

    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ScientificLabel(str, Enum):
    """Four-way project labels. Not native SciFact gold and not an execution status."""

    SUPPORTED = "supported"
    CONTRADICTED = "contradicted"
    UNADDRESSED = "unaddressed"
    UNDERDETERMINED = "underdetermined"


class SplitRole(str, Enum):
    """Project split roles. Public SciFact dev is held_out_local_eval, not a community test."""

    DEVELOPMENT = "development"
    CALIBRATION = "calibration"
    HELD_OUT_LOCAL_EVAL = "held_out_local_eval"
    OFFICIAL_TEST_UNLABELED = "official_test_unlabeled"


class EvidenceScope(str, Enum):
    D0 = "D0"
    D1 = "D1"
    D0_UNION_D1 = "D0_union_D1"
    NATIVE_SCIFACT = "native_scifact"


class AccessScope(str, Enum):
    D0 = "D0"
    D1 = "D1"
    D0_UNION_D1 = "D0_union_D1"
    CORPUS = "corpus"


class Provenance(str, Enum):
    ORIGINAL = "original"
    INDEPENDENT = "independent"
    CORPUS_GOLD = "corpus_gold"


class LabelSpace(str, Enum):
    SCIFACT_NATIVE = "scifact_native"
    MAVS_FOUR_WAY = "mavs_four_way"


class GoldProvenance(str, Enum):
    UPSTREAM_SCIFACT = "upstream_scifact"
    HUMAN_ANNOTATION = "human_annotation"
    NONE = "none"


class ClaimSource(BaseModel):
    """Dataset identity for a claim loaded from a frozen corpus."""

    model_config = ConfigDict(extra="forbid")

    dataset: str = Field(pattern=r"^scifact$")
    native_id: int
    split_role: SplitRole | None = None


class EvidenceOffsets(BaseModel):
    """Character offsets into the space-joined abstract, plus cited sentence indexes."""

    model_config = ConfigDict(extra="forbid")

    start: int = Field(ge=0)
    end: int = Field(ge=0)
    sentence_idxs: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def end_covers_start(self) -> EvidenceOffsets:
        if self.end < self.start:
            raise ValueError("offsets.end must be greater than or equal to offsets.start")
        if any(index < 0 for index in self.sentence_idxs):
            raise ValueError("sentence indexes must be >= 0")
        return self


class Run(BaseModel):
    """One validator execution. ``status`` is an execution status, not a scientific label."""

    model_config = ConfigDict(extra="forbid")

    run_id: str = Field(min_length=1)
    question_id: str | None = None
    split: str = Field(min_length=1)
    seed: int
    model_id: str = Field(min_length=1)
    model_revision: str | None = None
    prompt_hash: str = Field(pattern=_SHA256)
    corpus_hash: str = Field(pattern=_SHA256)
    config_hash: str = Field(pattern=_SHA256)
    timestamps: dict[str, Any] = Field(default_factory=dict)
    tokens: dict[str, Any] | None = None
    status: ExecutionStatus


class Claim(BaseModel):
    """Atomic claim. Decomposition fields stay empty until a later slice fills them."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    report_id: str | None = None
    exact_source_span: str | None = None
    normalized_claim: str = Field(min_length=1)
    subject: str | None = None
    relation: str | None = None
    object: str | None = None
    population: str | None = None
    comparator: str | None = None
    time: str | None = None
    units: str | None = None
    modality: str | None = None
    neutral_question: str | None = None
    asserted_answer: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    source: ClaimSource


class Evidence(BaseModel):
    """A cited passage. ``doc_id`` for SciFact is the S2ORC integer id."""

    model_config = ConfigDict(extra="forbid")

    doc_id: int | str
    doi: str | None = None
    pmid: str | None = None
    snapshot_hash: str = Field(pattern=_SHA256)
    text_span: str
    offsets: EvidenceOffsets | None = None
    query: str | None = None
    rank: int | None = None
    retrieval_round: int | None = None
    provenance: Provenance | None = None
    deduplication_group: str | None = None
    access_scope: AccessScope


class Judgment(BaseModel):
    """A label for one claim and evidence scope.

    ``label`` is the scientific or native-corpus label. ``execution_status``
    records timeouts and other failures. Those two fields are not interchangeable.
    """

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    evidence_scope: EvidenceScope
    label_space: LabelSpace
    label: str = Field(min_length=1)
    rationale_codes: list[str] = Field(default_factory=list)
    cited_span_ids: list[str] = Field(default_factory=list)
    raw_scores: dict[str, Any] | None = None
    calibrated_probabilities: dict[str, Any] | None = None
    execution_status: ExecutionStatus | None = None
    uncertainty_reasons: list[str] = Field(default_factory=list)
    gold_provenance: GoldProvenance = GoldProvenance.NONE

    @model_validator(mode="after")
    def separate_execution_status_from_label(self) -> Judgment:
        execution_values = {item.value for item in ExecutionStatus}
        if self.label.lower() in execution_values:
            raise ValueError(
                "Judgment.label cannot be an execution status; "
                "put timeout and other failures in execution_status"
            )
        if self.label_space is LabelSpace.MAVS_FOUR_WAY:
            allowed = {item.value for item in ScientificLabel}
            if self.label not in allowed:
                raise ValueError(
                    "mavs_four_way label must be supported, contradicted, "
                    "unaddressed, or underdetermined"
                )
        elif self.label_space is LabelSpace.SCIFACT_NATIVE:
            if self.label not in {"SUPPORT", "CONTRADICT"}:
                raise ValueError(
                    "scifact_native label must be SUPPORT or CONTRADICT; "
                    "do not invent four-way gold for SciFact"
                )
        return self


class ReportVerdict(BaseModel):
    """Report-level outcome after claim judgments are combined."""

    model_config = ConfigDict(extra="forbid")

    claim_coverage: dict[str, Any]
    central_claim_outcomes: list[Any]
    inference_link_status: list[Any]
    conflicts_d0_d1: list[Any]
    display_explanation: str
    limitations: list[str]
