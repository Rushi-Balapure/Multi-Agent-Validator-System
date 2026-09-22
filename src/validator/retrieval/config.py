"""Retrieval config. Extra keys are rejected so gold fields cannot ride along in YAML."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from validator.retrieval.errors import CorpusHashMismatch, RetrievalError
from validator.retrieval.paths import REPO_ROOT

_SHA256 = r"^[a-f0-9]{64}$"
_CLAIM_ID = re.compile(r"^scifact:\d+$")
# Research-plan round-2 rules. Recorded in config and locked; gather does not run them.
_ROUND2_START = (
    "unresolved_question",
    "scope_mismatch",
    "contradictory_evidence",
)
_ROUND2_STOP = (
    "exhausted_budget",
    "no_new_eligible_documents",
    "complete_bounded_evidence",
)


class QueryTemplates(BaseModel):
    """The three research-plan query forms. Each template must include ``{text}``."""

    model_config = ConfigDict(extra="forbid")

    open_inquiry: str = Field(min_length=1)
    scope_measurement: str = Field(min_length=1)
    limitations_null: str = Field(min_length=1)

    @model_validator(mode="after")
    def templates_include_text(self) -> QueryTemplates:
        for name in ("open_inquiry", "scope_measurement", "limitations_null"):
            if "{text}" not in getattr(self, name):
                raise ValueError(f"{name} template must contain {{text}}")
        return self


class Round2Flags(BaseModel):
    """Prep notes for a later retrieval round. This MR does not run round 2.

    ``enabled`` is locked false. ``start_when`` and ``stop_when`` are the
    research-plan rules (unresolved question, scope mismatch, or contradictory
    evidence; stop on exhausted budget, no new eligible documents, or a
    complete bounded evidence record). ``retrieval_round`` on the parent
    config stays 1.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: Literal[False] = False
    start_when: list[str] = Field(default_factory=lambda: list(_ROUND2_START))
    stop_when: list[str] = Field(default_factory=lambda: list(_ROUND2_STOP))

    @model_validator(mode="after")
    def locked_prep_notes(self) -> Round2Flags:
        if tuple(self.start_when) != _ROUND2_START:
            raise ValueError(
                "round2.start_when is locked to unresolved_question, "
                "scope_mismatch, contradictory_evidence"
            )
        if tuple(self.stop_when) != _ROUND2_STOP:
            raise ValueError(
                "round2.stop_when is locked to exhausted_budget, "
                "no_new_eligible_documents, complete_bounded_evidence"
            )
        return self


class RrfFlags(BaseModel):
    """Prep notes for reciprocal-rank fusion. This MR does not fuse ranks.

    ``enabled`` is locked false and ``k`` is locked to 60, the usual
    ``1 / (k + rank)`` constant. Product rerank stays ``max_bm25``.
    """

    model_config = ConfigDict(extra="forbid")

    enabled: Literal[False] = False
    k: Literal[60] = 60


class RetrievalConfig(BaseModel):
    """BM25 gather settings for the locked SciFact corpus."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(pattern=r"^scifact-bm25-gather-v1$")
    dataset: str = Field(pattern=r"^scifact$")
    doc_id_scheme: str = Field(pattern=r"^scifact_s2orc_integer$")
    corpus_config: str = Field(min_length=1)
    corpus_jsonl: str = Field(min_length=1)
    corpus_hash: str = Field(pattern=_SHA256)
    claims_jsonl: str = Field(min_length=1)
    development_manifest: str = Field(min_length=1)
    index_path: str = Field(min_length=1)
    k1: float = Field(gt=0)
    b: float = Field(ge=0, le=1)
    epsilon: float = Field(gt=0)
    top_k_per_query: int = Field(ge=1, le=20)
    max_passages: int = Field(ge=1, le=8)
    retrieval_round: int = Field(ge=1, le=1)
    tokenizer: str = Field(pattern=r"^alnum_lower_v1$")
    rerank: str = Field(pattern=r"^max_bm25$")
    query_templates: QueryTemplates
    fixed_claim_ids: list[str] = Field(min_length=10, max_length=10)
    round2: Round2Flags = Field(default_factory=Round2Flags)
    rrf: RrfFlags = Field(default_factory=RrfFlags)

    @model_validator(mode="after")
    def ten_project_claim_ids(self) -> RetrievalConfig:
        if len(set(self.fixed_claim_ids)) != 10:
            raise ValueError("fixed_claim_ids must be 10 unique project claim ids")
        for claim_id in self.fixed_claim_ids:
            if _CLAIM_ID.fullmatch(claim_id) is None:
                raise ValueError(
                    f"claim_id must be a project id such as scifact:2, got {claim_id!r}"
                )
        return self

    def resolve(self, relative: str) -> Path:
        path = Path(relative)
        if path.is_absolute():
            return path
        return (REPO_ROOT / path).resolve()


def load_retrieval_config(path: Path) -> RetrievalConfig:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RetrievalError(f"{path} is not a retrieval config mapping")
    return RetrievalConfig.model_validate(loaded)


def read_corpus_contract(path: Path) -> tuple[str, str]:
    """Return ``(corpus_hash, doc_id_scheme)`` from a corpus-lock YAML file."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise RetrievalError(f"{path} is not a corpus config mapping")
    corpus_hash = loaded.get("corpus_hash")
    scheme = loaded.get("doc_id_scheme")
    if not isinstance(corpus_hash, str) or re.fullmatch(_SHA256, corpus_hash) is None:
        raise RetrievalError(f"{path} corpus_hash is not a lowercase sha256")
    if scheme != "scifact_s2orc_integer":
        raise RetrievalError(f"{path} doc_id_scheme must be scifact_s2orc_integer")
    return corpus_hash, scheme


def verify_corpus_lock(config: RetrievalConfig) -> str:
    """Hash ``corpus.jsonl`` and refuse to continue when it misses the pin.

    The file hash, the retrieval config, and ``configs/corpus/scifact.yaml``
    (or the test stand-in) must all three agree. This runs before any index
    write.
    """
    from data.pins.scifact.download_verify import file_sha256

    corpus_path = config.resolve(config.corpus_jsonl)
    if corpus_path.name != "corpus.jsonl":
        raise RetrievalError(
            "corpus path must be named corpus.jsonl so the corpus-lock loader can read it"
        )
    if not corpus_path.is_file():
        raise CorpusHashMismatch(f"refusing to index: missing corpus file {corpus_path}")
    actual = file_sha256(corpus_path)
    if actual != config.corpus_hash:
        raise CorpusHashMismatch(
            "refusing to index: "
            f"{corpus_path} sha256 {actual} != pinned corpus_hash {config.corpus_hash}"
        )
    declared_hash, scheme = read_corpus_contract(config.resolve(config.corpus_config))
    if declared_hash != config.corpus_hash:
        raise CorpusHashMismatch(
            "refusing to index: "
            f"retrieval corpus_hash {config.corpus_hash} != "
            f"{config.corpus_config} corpus_hash {declared_hash}"
        )
    if scheme != config.doc_id_scheme:
        raise CorpusHashMismatch(
            "refusing to index: "
            f"doc_id_scheme {scheme} != {config.doc_id_scheme}"
        )
    return actual
