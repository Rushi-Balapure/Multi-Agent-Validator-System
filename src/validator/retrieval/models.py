"""Evidence bundles for one independent retrieval round.

Passages are :class:`validator.schemas.Evidence` records plus the BM25 score
that ranked them. ``deduplication_group`` is the schema name for the dedupe
group (``s2orc:{doc_id}``).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from validator.schemas import AccessScope, Evidence, Provenance

QueryForm = Literal["open_inquiry", "scope_measurement", "limitations_null"]
QUERY_FORMS: tuple[QueryForm, ...] = (
    "open_inquiry",
    "scope_measurement",
    "limitations_null",
)
_SHA256 = r"^[a-f0-9]{64}$"
_CLAIM_ID = r"^scifact:\d+$"
TOP_K_CEILING = 20
PASSAGE_CEILING = 8


def normalize_passage_text(text: str) -> str:
    """Case-fold and collapse whitespace so repeated abstracts dedupe."""
    return " ".join(text.casefold().split())


class RetrievedPassage(Evidence):
    """One D1 passage. ``score`` is retrieval metadata; the other fields are Evidence."""

    score: float

    @model_validator(mode="after")
    def independent_d1_passage(self) -> RetrievedPassage:
        Evidence.model_validate(self.model_dump(exclude={"score"}))
        if not isinstance(self.doc_id, int) or isinstance(self.doc_id, bool):
            raise ValueError("SciFact doc_id must be the S2ORC integer")
        if self.access_scope is not AccessScope.D1:
            raise ValueError("retrieved passages must use access_scope D1")
        if self.provenance is not Provenance.INDEPENDENT:
            raise ValueError("retrieved passages must use provenance independent")
        if self.offsets is None:
            raise ValueError("retrieved passages require offsets")
        if self.rank is None or self.rank < 1:
            raise ValueError("retrieved passages require rank >= 1")
        if self.retrieval_round is None or self.retrieval_round < 1:
            raise ValueError("retrieved passages require retrieval_round >= 1")
        if not self.query:
            raise ValueError("retrieved passages require the query that selected them")
        if self.deduplication_group != f"s2orc:{self.doc_id}":
            raise ValueError("deduplication_group must be s2orc:{doc_id}")
        return self


class QueryHit(BaseModel):
    """One pre-dedupe hit. ``rank`` is 1-based within that query."""

    model_config = ConfigDict(extra="forbid")

    doc_id: int
    rank: int = Field(ge=1)
    score: float


class QueryLog(BaseModel):
    """Query text plus the top hits for one protocol form."""

    model_config = ConfigDict(extra="forbid")

    form: QueryForm
    query: str = Field(min_length=1)
    hits: list[QueryHit]

    @model_validator(mode="after")
    def hit_cap_and_ranks(self) -> QueryLog:
        if len(self.hits) > TOP_K_CEILING:
            raise ValueError(f"each query keeps at most {TOP_K_CEILING} hits")
        ranks = [hit.rank for hit in self.hits]
        if ranks != list(range(1, len(self.hits) + 1)):
            raise ValueError("query hit ranks must be 1..n in order")
        return self


class EvidenceBundle(BaseModel):
    """Independent evidence for one claim and one retrieval round."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(pattern=_CLAIM_ID)
    query: str = Field(min_length=1)
    queries: list[QueryLog]
    retrieval_round: int = Field(ge=1)
    corpus_hash: str = Field(pattern=_SHA256)
    passages: list[RetrievedPassage]

    @model_validator(mode="after")
    def bundle_contract(self) -> EvidenceBundle:
        if len(self.passages) > PASSAGE_CEILING:
            raise ValueError(f"at most {PASSAGE_CEILING} passages")
        forms = [item.form for item in self.queries]
        if forms != list(QUERY_FORMS):
            raise ValueError(
                "queries must be open_inquiry, scope_measurement, limitations_null"
            )
        doc_ids = [passage.doc_id for passage in self.passages]
        if len(doc_ids) != len(set(doc_ids)):
            raise ValueError("passages must be deduped by doc_id")
        groups = [passage.deduplication_group for passage in self.passages]
        if len(groups) != len(set(groups)):
            raise ValueError("passages must be deduped by deduplication_group")
        norms = [normalize_passage_text(passage.text_span) for passage in self.passages]
        if len(norms) != len(set(norms)):
            raise ValueError("passages must be deduped by normalized text")
        ranks = [passage.rank for passage in self.passages]
        if ranks != list(range(1, len(self.passages) + 1)):
            raise ValueError("passage ranks must be 1..n")
        scores = [passage.score for passage in self.passages]
        if scores != sorted(scores, reverse=True):
            raise ValueError("passages must be reranked by descending score")
        for passage in self.passages:
            if passage.retrieval_round != self.retrieval_round:
                raise ValueError("passage retrieval_round must match the bundle")
        return self
