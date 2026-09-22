"""Non-gold proposer citations as D0 for Stack V ``--gather``.

SciFact native claims carry ``cited_doc_ids`` (original S2ORC citation ids)
separately from gold ``evidence`` SUPPORT/CONTRADICT rationales. This module
joins those citation ids to ``corpus.jsonl`` abstracts via
``data.scifact_loader`` and returns ``Evidence`` with
``provenance=original`` and ``access_scope=D0``.

Hard rules:

- Never copy gold same-evidence sentence spans into D0.
- Never pass gold labels into reader/gather payloads (this module does not
  return labels at all).
- Retrieval Wing ``gather`` stays D1-only; it does not ingest these ids.
"""

from __future__ import annotations

from pathlib import Path

from data.scifact_loader import (
    SciFactDataError,
    abstract_text_and_spans,
    index_claims,
    load_corpus,
    load_jsonl,
    snapshot_hash,
)
from validator.retrieve import native_id_from_claim_id
from validator.retrieval.errors import RetrievalError
from validator.schemas import AccessScope, Evidence, EvidenceOffsets, Provenance


class CitedD0Error(Exception):
    """Cited-doc D0 join failed (missing claim, missing corpus doc, or empty citations)."""


def evidence_from_cited_doc_ids(
    native: dict,
    corpus: dict[int, dict],
    hashes: dict[int, str] | None = None,
) -> list[Evidence]:
    """Build ORIGINAL/D0 passages from ``cited_doc_ids`` only.

    Ignores the native ``evidence`` object (gold SUPPORT/CONTRADICT rationales).
    The gold field may be present on ``native`` but is never read here.
    """
    if not isinstance(native, dict):
        raise CitedD0Error("native claim must be a mapping")
    claim_id = native.get("id")
    cited = native.get("cited_doc_ids")
    if not isinstance(cited, list) or not cited:
        raise CitedD0Error(
            f"claim {claim_id!r} is missing non-empty cited_doc_ids; "
            "gather D0 requires original proposer citations"
        )
    digests = hashes if hashes is not None else {
        doc_id: snapshot_hash(doc) for doc_id, doc in corpus.items()
    }
    passages: list[Evidence] = []
    for doc_id in cited:
        if not isinstance(doc_id, int) or isinstance(doc_id, bool):
            raise CitedD0Error(f"claim {claim_id!r} has a non-integer cited doc id {doc_id!r}")
        try:
            doc = corpus[doc_id]
        except KeyError as exc:
            raise CitedD0Error(
                f"claim {claim_id} cites doc_id {doc_id}, which is not in corpus.jsonl"
            ) from exc
        try:
            digest = digests[doc_id]
        except KeyError as exc:
            raise CitedD0Error(
                f"claim {claim_id} cites doc_id {doc_id}, which has no snapshot_hash"
            ) from exc
        passages.append(_document_evidence(doc, digest))
    return passages


def _document_evidence(doc: dict, digest: str) -> Evidence:
    """Full-abstract ORIGINAL/D0 passage. Matches ``data.scifact_loader`` same-evidence shape."""
    text, _spans = abstract_text_and_spans(doc["abstract"])
    return Evidence(
        doc_id=doc["doc_id"],
        snapshot_hash=digest,
        text_span=text,
        offsets=EvidenceOffsets(
            start=0,
            end=len(text),
            sentence_idxs=list(range(len(doc["abstract"]))),
        ),
        provenance=Provenance.ORIGINAL,
        deduplication_group=f"s2orc:{doc['doc_id']}",
        access_scope=AccessScope.D0,
    )


class CitedD0Index:
    """Corpus + claims index for batch gather. Loads once per run."""

    def __init__(self, root: Path, claims_jsonl: Path) -> None:
        raw_dir = root / "data" / "raw" / "scifact"
        try:
            self._corpus = load_corpus(raw_dir)
        except (SciFactDataError, OSError) as exc:
            raise CitedD0Error(f"failed to load corpus.jsonl under {raw_dir}: {exc}") from exc
        self._hashes = {doc_id: snapshot_hash(doc) for doc_id, doc in self._corpus.items()}
        try:
            self._claims = index_claims(load_jsonl(claims_jsonl), claims_jsonl.name)
        except (SciFactDataError, OSError) as exc:
            raise CitedD0Error(f"failed to load claims from {claims_jsonl}: {exc}") from exc
        self._claims_path = claims_jsonl

    def for_claim(self, claim_id: str) -> list[Evidence]:
        """Return ORIGINAL/D0 abstracts for one project claim id."""
        try:
            native_id = native_id_from_claim_id(claim_id)
        except RetrievalError as exc:
            raise CitedD0Error(str(exc)) from exc
        try:
            native = self._claims[native_id]
        except KeyError as exc:
            raise CitedD0Error(
                f"{claim_id} is missing from {self._claims_path}"
            ) from exc
        # Gold evidence keys stay on the native record; evidence_from_cited_doc_ids
        # never reads them.
        return evidence_from_cited_doc_ids(native, self._corpus, self._hashes)


def load_cited_d0_index(root: Path, claims_jsonl: Path) -> CitedD0Index:
    """Construct a batch index. Fail closed if corpus or claims cannot be joined."""
    return CitedD0Index(root, claims_jsonl)
