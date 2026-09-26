"""Cited-document connected components."""

from __future__ import annotations

import pytest

from evaluation.families import (
    FamilyError,
    attach_claim_families,
    connected_components,
)


def test_shared_docs_merge_and_isolated_claims_stay_singleton():
    families = connected_components(
        {
            "scifact:1": [10, 11],
            "scifact:2": [11],
            "scifact:3": [99],
            "scifact:4": [],
        }
    )
    assert families["scifact:1"] == families["scifact:2"] == "cited:scifact:1"
    assert families["scifact:3"] == "cited:scifact:3"
    assert families["scifact:4"] == "cited:scifact:4"


def test_attach_writes_claim_family_when_missing():
    families = {"c1": "cited:c1", "c2": "cited:c1"}
    rows = attach_claim_families(
        [{"claim_id": "c1", "label": "NEI"}, {"claim_id": "c2", "label": "SUPPORT"}],
        families,
    )
    assert rows[0]["claim_family"] == "cited:c1"
    assert rows[1]["claim_family"] == "cited:c1"


def test_attach_keeps_an_existing_question_family():
    rows = attach_claim_families(
        [{"claim_id": "c1", "question_family": "given"}],
        {"c1": "cited:c1"},
    )
    assert rows[0]["question_family"] == "given"
    assert "claim_family" not in rows[0]


def test_missing_claim_is_an_error():
    with pytest.raises(FamilyError, match="no cited-doc family"):
        attach_claim_families([{"claim_id": "missing"}], {"c1": "cited:c1"})
