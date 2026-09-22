"""Cited_doc_ids → ORIGINAL/D0 passages for Stack V gather (non-gold)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.scifact_loader import bundle_claim, snapshot_hash
from validator.schemas import AccessScope, Provenance
from validator.validator_v.cited_d0 import (
    CitedD0Error,
    CitedD0Index,
    evidence_from_cited_doc_ids,
)


def _doc(doc_id: int = 10, sentences: list[str] | None = None) -> dict:
    return {
        "doc_id": doc_id,
        "title": "Vitamin C trial",
        "abstract": sentences
        or [
            "Adults took vitamin C during one winter.",
            "Cold duration was shorter in the treatment arm.",
        ],
        "structured": False,
    }


def _native(
    claim_id: int = 1,
    *,
    cited: list[int] | None = None,
    evidence: dict | None = None,
) -> dict:
    return {
        "id": claim_id,
        "claim": "Vitamin C shortens colds.",
        "evidence": evidence
        if evidence is not None
        else {
            "10": [
                {
                    "label": "SUPPORT",
                    "sentences": [1],
                }
            ]
        },
        "cited_doc_ids": cited if cited is not None else [10],
    }


def test_cited_doc_ids_become_original_d0_full_abstracts():
    doc = _doc()
    digest = snapshot_hash(doc)
    passages = evidence_from_cited_doc_ids(_native(), {10: doc}, {10: digest})
    assert len(passages) == 1
    passage = passages[0]
    assert passage.doc_id == 10
    assert passage.provenance is Provenance.ORIGINAL
    assert passage.access_scope is AccessScope.D0
    assert passage.snapshot_hash == digest
    assert passage.text_span == (
        "Adults took vitamin C during one winter. "
        "Cold duration was shorter in the treatment arm."
    )
    assert passage.offsets.sentence_idxs == [0, 1]
    assert passage.deduplication_group == "s2orc:10"


def test_gold_evidence_fields_never_appear_in_d0_construction():
    """Gold SUPPORT/CONTRADICT sentence spans must not become D0."""
    doc = _doc()
    digest = snapshot_hash(doc)
    native = _native(
        evidence={
            "10": [
                {
                    "label": "SUPPORT",
                    "sentences": [1],
                    "confidential_gold_marker": "MUST_NOT_LEAK",
                }
            ]
        }
    )
    passages = evidence_from_cited_doc_ids(native, {10: doc}, {10: digest})
    assert len(passages) == 1
    # Full abstract, not gold sentence 1 alone.
    assert passages[0].text_span != doc["abstract"][1]
    assert "Cold duration was shorter" in passages[0].text_span
    assert "Adults took vitamin C" in passages[0].text_span
    assert passages[0].provenance is Provenance.ORIGINAL
    assert passages[0].provenance is not Provenance.CORPUS_GOLD
    blob = json.dumps(passages[0].model_dump(mode="json"))
    assert "MUST_NOT_LEAK" not in blob
    assert "SUPPORT" not in blob
    assert "CONTRADICT" not in blob
    assert "corpus_gold" not in blob

    bundle = bundle_claim(
        native,
        split_role="development",
        corpus={10: doc},
        hashes={10: digest},
    )
    gold_spans = [item.text_span for item in bundle.gold_evidence]
    assert gold_spans == [doc["abstract"][1]]
    assert passages[0].text_span != gold_spans[0]
    assert [item.provenance for item in bundle.gold_evidence] == [Provenance.CORPUS_GOLD]


def test_empty_cited_doc_ids_fail_closed():
    doc = _doc()
    with pytest.raises(CitedD0Error, match="cited_doc_ids"):
        evidence_from_cited_doc_ids(_native(cited=[]), {10: doc}, {10: snapshot_hash(doc)})


def test_missing_corpus_doc_is_a_join_failure():
    with pytest.raises(CitedD0Error, match="not in corpus.jsonl"):
        evidence_from_cited_doc_ids(_native(cited=[99]), {10: _doc()}, {})


def test_cited_d0_index_reads_claims_jsonl(tmp_path: Path):
    raw = tmp_path / "data" / "raw" / "scifact"
    raw.mkdir(parents=True)
    doc = _doc(42, ["Alpha sentence.", "Beta sentence."])
    (raw / "corpus.jsonl").write_text(
        json.dumps(doc, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    claim = _native(
        7,
        cited=[42],
        evidence={"42": [{"label": "CONTRADICT", "sentences": [0]}]},
    )
    claims_path = raw / "claims_train.jsonl"
    claims_path.write_text(json.dumps(claim) + "\n", encoding="utf-8")

    index = CitedD0Index(tmp_path, claims_path)
    passages = index.for_claim("scifact:7")
    assert [item.doc_id for item in passages] == [42]
    assert passages[0].provenance is Provenance.ORIGINAL
    assert passages[0].access_scope is AccessScope.D0
    assert passages[0].text_span == "Alpha sentence. Beta sentence."
    assert passages[0].text_span != "Alpha sentence."
    dumped = json.dumps([item.model_dump(mode="json") for item in passages])
    assert "CONTRADICT" not in dumped
    assert "corpus_gold" not in dumped


def test_cited_d0_index_missing_claim_fails():
    # Constructed with empty claims file after a real corpus write is awkward;
    # exercise for_claim KeyError via a minimal index mock path.
    with pytest.raises(CitedD0Error, match="missing"):
        # Build a tiny fake by subclassing behavior through empty claims.
        class Empty(CitedD0Index):
            def __init__(self) -> None:  # noqa: D401
                self._corpus = {}
                self._hashes = {}
                self._claims = {}
                self._claims_path = Path("claims.jsonl")

        Empty().for_claim("scifact:0")
