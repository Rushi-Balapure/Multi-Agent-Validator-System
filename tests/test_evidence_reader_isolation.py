"""Reader isolation: asserted answers, conclusions, and gold labels stay out."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from validator.evidence_reader import (
    FORBIDDEN_READER_KEYS,
    IsolationError,
    ReaderPassage,
    read_evidence,
    shuffle_passages,
)
from validator.fixture_pipeline import load_fixture, reader_payload

ROOT = Path(__file__).resolve().parents[1]
COMPLETE = ROOT / "tests" / "fixtures" / "judgment" / "complete.json"
LEAK = "LEAK_ASSERTED_ANSWER"


def _passage(span_id: str, doc_id: int, text: str) -> dict:
    return {"span_id": span_id, "doc_id": doc_id, "text": text}


def test_forbidden_reader_keys_include_asserted_answer():
    assert "asserted_answer" in FORBIDDEN_READER_KEYS
    assert "frozen_conclusion" in FORBIDDEN_READER_KEYS
    assert "gold_labels" in FORBIDDEN_READER_KEYS


def test_reader_rejects_asserted_answer():
    payload = {
        "neutral_question": "What did abstracts report about compound MX-42?",
        "passages": [_passage("D1:1:0-5", 1, "compound MX-42 memory retention")],
        "asserted_answer": LEAK,
    }
    with pytest.raises(IsolationError, match="asserted_answer"):
        read_evidence(payload)


@pytest.mark.parametrize(
    "key",
    ["frozen_conclusion", "conclusion", "gold_labels", "gold_label", "normalized_claim"],
)
def test_reader_rejects_claim_and_gold_keys(key: str):
    payload = {
        "neutral_question": "What did abstracts report about compound MX-42 in mice?",
        "passages": [_passage("D1:1:0-8", 1, "mouse model compound MX-42 memory")],
        key: "not for the reader",
    }
    with pytest.raises(IsolationError):
        read_evidence(payload)


def test_pipeline_reader_payload_excludes_asserted_answer():
    fixture = load_fixture(COMPLETE)
    assert fixture.claim.asserted_answer is not None
    assert LEAK in fixture.claim.asserted_answer
    payload = reader_payload(fixture.claim, fixture.d1_bundle)
    assert set(payload) == {"neutral_question", "passages"}
    assert "asserted_answer" not in json.dumps(payload)
    assert LEAK not in json.dumps(payload)
    for passage in payload["passages"]:
        assert set(passage) == {"span_id", "doc_id", "text"}
    sealed = read_evidence(payload)
    dumped = sealed.model_dump(mode="json")
    assert "asserted_answer" not in dumped
    assert LEAK not in json.dumps(dumped)
    assert sealed.cited_span_ids
    assert all(span_id.startswith("D1:") for span_id in sealed.cited_span_ids)


def test_asserted_answer_does_not_change_the_seal():
    fixture = load_fixture(COMPLETE)
    first = read_evidence(reader_payload(fixture.claim, fixture.d1_bundle))
    other = fixture.model_copy(
        update={
            "claim": fixture.claim.model_copy(
                update={"asserted_answer": "a different asserted answer"}
            )
        }
    )
    second = read_evidence(reader_payload(other.claim, other.d1_bundle))
    assert first.seal == second.seal
    assert first.answer == second.answer


def test_shuffle_is_deterministic_and_ignores_claim_text():
    passages = [
        ReaderPassage(span_id="D1:1:0-1", doc_id=1, text="alpha"),
        ReaderPassage(span_id="D1:2:0-1", doc_id=2, text="beta"),
        ReaderPassage(span_id="D1:3:0-1", doc_id=3, text="gamma"),
    ]
    question = "What did abstracts report about compound MX-42 memory retention?"
    once = shuffle_passages(passages, question)
    twice = shuffle_passages(passages, question)
    assert [item.span_id for item in once] == [item.span_id for item in twice]
    assert sorted(item.span_id for item in once) == [
        "D1:1:0-1",
        "D1:2:0-1",
        "D1:3:0-1",
    ]
    assert [item.span_id for item in once] != [item.span_id for item in passages]
