"""Evidence text for the claim-visible baselines."""

from __future__ import annotations

from validator.retrieval.models import EvidenceBundle
from validator.same_evidence.inputs import PredictInput

ADAPTATIONS = ("B0", "B1", "B3", "O")


def format_d0_abstracts(item: PredictInput) -> str:
    """All cited abstracts, in cited_doc_ids order. Rationales are omitted."""
    parts: list[str] = []
    for doc in item.gold_evidence_bundle:
        abstract = " ".join(doc.abstract)
        parts.append(f"[doc {doc.doc_id}] {doc.title}\n{abstract}")
    return "\n\n".join(parts)


def format_oracle_rationales(item: PredictInput) -> str:
    """Gold rationale sentences only. Empty when the claim is NEI-eligible."""
    parts: list[str] = []
    for doc in item.gold_evidence_bundle:
        if not doc.rationales:
            continue
        indexes: list[int] = []
        for rationale in doc.rationales:
            indexes.extend(rationale.sentences)
        unique = sorted(set(indexes))
        sentences = [doc.abstract[index] for index in unique if 0 <= index < len(doc.abstract)]
        if not sentences:
            continue
        parts.append(f"[doc {doc.doc_id}] {doc.title}\n" + " ".join(sentences))
    return "\n\n".join(parts)


def format_d1_passages(bundle: EvidenceBundle | None) -> str:
    if bundle is None or not bundle.passages:
        return ""
    parts = []
    for passage in bundle.passages:
        parts.append(f"[doc {passage.doc_id} rank {passage.rank}]\n{passage.text_span}")
    return "\n\n".join(parts)


def evidence_text(
    item: PredictInput,
    adaptation: str,
    *,
    d1_bundle: EvidenceBundle | None = None,
) -> str:
    if adaptation == "B0":
        return ""
    if adaptation == "B1":
        return format_d0_abstracts(item)
    if adaptation == "B3":
        return format_d1_passages(d1_bundle)
    if adaptation == "O":
        return format_oracle_rationales(item)
    raise ValueError(f"unknown adaptation {adaptation!r}; expected one of {ADAPTATIONS}")
