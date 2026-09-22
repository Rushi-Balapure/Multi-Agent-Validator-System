"""Blind evidence reader.

Inputs are a neutral question and D1 passage text. The reader seals an
evidence-only answer and its cited span ids before any claim is revealed.
The default fixture reader quotes overlapping passages and does not call a
model. ``validator.live_judgment`` may call a local model, and it still
rejects any payload that crosses this boundary before the request is sent.
"""

from __future__ import annotations

import hashlib
import json
import random
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from validator.label_policy import content_tokens

_SHA256 = r"^[a-f0-9]{64}$"

# Keys that would reveal the claim, the frozen conclusion, or gold D0 labels.
FORBIDDEN_READER_KEYS = frozenset(
    {
        "asserted_answer",
        "frozen_conclusion",
        "conclusion",
        "conclusions",
        "gold",
        "gold_label",
        "gold_labels",
        "gold_d0",
        "gold_evidence",
        "normalized_claim",
        "exact_source_span",
        "label",
        "labels",
        "label_space",
        "d0",
        "d0_evidence",
        "dependencies",
        "claim",
        "claim_id",
    }
)


class IsolationError(ValueError):
    """A reader input crossed the evidence-only boundary."""


class ReaderPassage(BaseModel):
    """One shuffled D1 passage. Retrieval rank and the claim are not included."""

    model_config = ConfigDict(extra="forbid")

    span_id: str = Field(min_length=1)
    doc_id: int
    text: str = Field(min_length=1)


class EvidenceReaderInput(BaseModel):
    """The only object the reader accepts."""

    model_config = ConfigDict(extra="forbid")

    neutral_question: str = Field(min_length=1)
    passages: list[ReaderPassage]


def compute_seal(neutral_question: str, answer: str, cited_span_ids: list[str]) -> str:
    """Hash the evidence-only body. The claim is not part of the seal."""
    payload = json.dumps(
        {
            "answer": answer,
            "cited_span_ids": list(cited_span_ids),
            "neutral_question": neutral_question,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SealedEvidenceRecord(BaseModel):
    """Evidence-only answer sealed before the judge sees the claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    neutral_question: str = Field(min_length=1)
    answer: str = Field(min_length=1)
    cited_span_ids: list[str]
    seal: str = Field(pattern=_SHA256)

    @model_validator(mode="after")
    def seal_matches_body(self) -> SealedEvidenceRecord:
        expected = compute_seal(self.neutral_question, self.answer, self.cited_span_ids)
        if self.seal != expected:
            raise ValueError(
                "sealed evidence record hash does not match its answer and span ids"
            )
        return self

    @classmethod
    def from_body(
        cls,
        *,
        neutral_question: str,
        answer: str,
        cited_span_ids: list[str],
    ) -> SealedEvidenceRecord:
        return cls(
            neutral_question=neutral_question,
            answer=answer,
            cited_span_ids=list(cited_span_ids),
            seal=compute_seal(neutral_question, answer, cited_span_ids),
        )


def _walk_keys(value: Any):
    if isinstance(value, dict):
        for key, child in value.items():
            yield str(key)
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def assert_reader_boundary(payload: dict[str, Any]) -> EvidenceReaderInput:
    """Reject claim text, asserted answers, conclusions, and gold labels."""
    if not isinstance(payload, dict):
        raise IsolationError(
            "evidence reader accepts only a mapping with neutral_question and passages"
        )
    leaked = sorted(set(_walk_keys(payload)) & FORBIDDEN_READER_KEYS)
    if leaked:
        raise IsolationError(
            "evidence reader rejects claim, conclusion, and gold-label fields: "
            + ", ".join(leaked)
        )
    try:
        return EvidenceReaderInput.model_validate(payload)
    except ValidationError as exc:
        raise IsolationError(
            "evidence reader input must contain only neutral_question and passages"
        ) from exc


def shuffle_passages(
    passages: list[ReaderPassage],
    neutral_question: str,
) -> list[ReaderPassage]:
    """Shuffle from the question and span ids. The claim is not a seed input."""
    material = neutral_question + "\n" + ",".join(passage.span_id for passage in passages)
    seed = int.from_bytes(hashlib.sha256(material.encode("utf-8")).digest()[:8], "big")
    shuffled = list(passages)
    random.Random(seed).shuffle(shuffled)
    return shuffled


def read_evidence(payload: dict[str, Any]) -> SealedEvidenceRecord:
    """Read shuffled D1 passages and seal the evidence-only record.

    The payload is rejected when it contains ``asserted_answer``, a frozen
    conclusion, or gold D0 labels. The returned record has no claim field.
    """
    parsed = assert_reader_boundary(payload)
    shuffled = shuffle_passages(parsed.passages, parsed.neutral_question)
    question_tokens = content_tokens(parsed.neutral_question)
    cited = [
        passage
        for passage in shuffled
        if len(question_tokens & content_tokens(passage.text)) >= 2
    ]
    if cited:
        answer = " ".join(f"{passage.text} [{passage.span_id}]" for passage in cited)
        cited_ids = [passage.span_id for passage in cited]
    else:
        answer = "No reviewed passage shares content terms with the neutral question."
        cited_ids = []
    return SealedEvidenceRecord.from_body(
        neutral_question=parsed.neutral_question,
        answer=answer,
        cited_span_ids=cited_ids,
    )
