"""D0 citation auditor: missing citations fail, and D1 cannot repair them."""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from validator.citation_auditor import audit_citations, rollup_adequacy
from validator.evidence_reader import IsolationError
from validator.fixture_pipeline import load_fixture
from validator.schemas import (
    AccessScope,
    Evidence,
    EvidenceOffsets,
    ExecutionStatus,
    Provenance,
    ScientificLabel,
)

ROOT = Path(__file__).resolve().parents[1]
COMPLETE = ROOT / "tests" / "fixtures" / "judgment" / "complete.json"


def test_auditor_signature_is_claim_and_d0_only():
    assert list(inspect.signature(audit_citations).parameters) == ["claim", "d0_evidence"]
    source = (ROOT / "src" / "validator" / "citation_auditor.py").read_text(encoding="utf-8")
    assert "EvidenceBundle" not in source
    assert "validator.retrieval" not in source
    assert "validator.judge" not in source


def test_missing_citation_fails_auditor():
    fixture = load_fixture(COMPLETE)
    audit = audit_citations(fixture.claim, [])
    assert audit.judgment.evidence_scope.value == "D0"
    assert audit.judgment.label_space.value == "mavs_four_way"
    assert audit.judgment.label == ScientificLabel.UNADDRESSED.value
    assert audit.judgment.execution_status is ExecutionStatus.FAILED
    assert audit.judgment.label not in {item.value for item in ExecutionStatus}
    assert audit.flags
    assert audit.flags[0].adequacy == "inadequate"
    assert "missing_required_citation" in audit.flags[0].defects
    assert rollup_adequacy(audit.flags) == "inadequate"


def test_empty_citation_span_fails_auditor():
    fixture = load_fixture(COMPLETE)
    empty = Evidence(
        doc_id=770001,
        snapshot_hash="ab" * 32,
        text_span="",
        provenance=Provenance.ORIGINAL,
        access_scope=AccessScope.D0,
    )
    audit = audit_citations(fixture.claim, [empty])
    assert audit.judgment.execution_status is ExecutionStatus.FAILED
    assert any("missing_required_citation" in flag.defects for flag in audit.flags)
    assert rollup_adequacy(audit.flags) == "inadequate"


def test_faithful_d0_is_adequate_and_completed():
    fixture = load_fixture(COMPLETE)
    audit = audit_citations(fixture.claim, fixture.d0_evidence)
    assert audit.judgment.execution_status is ExecutionStatus.COMPLETED
    assert audit.judgment.label == ScientificLabel.SUPPORTED.value
    assert audit.flags[0].adequacy == "adequate"
    assert audit.flags[0].defects == []
    assert audit.flags[0].span_id is not None
    assert audit.judgment.cited_span_ids == [audit.flags[0].span_id]


def test_contradicting_d0_is_not_repaired():
    """A supporting sentence that is not in D0 must not change the audit."""
    fixture = load_fixture(COMPLETE)
    text = (
        "In the mouse model, compound MX-42 decreased memory retention "
        "compared with vehicle."
    )
    contradicting = fixture.d0_evidence[0].model_copy(
        update={
            "text_span": text,
            "offsets": EvidenceOffsets(start=0, end=len(text), sentence_idxs=[0]),
        }
    )
    audit = audit_citations(fixture.claim, [contradicting])
    assert audit.judgment.label == ScientificLabel.CONTRADICTED.value
    assert audit.judgment.execution_status is ExecutionStatus.COMPLETED
    assert audit.flags[0].adequacy == "inadequate"
    with pytest.raises(TypeError):
        audit_citations(fixture.claim, [contradicting], fixture.d1_bundle)  # type: ignore[call-arg]


def test_auditor_rejects_d1_evidence():
    fixture = load_fixture(COMPLETE)
    passage = fixture.d1_bundle.passages[0]
    smuggled = Evidence.model_validate(passage.model_dump(exclude={"score"}))
    with pytest.raises(IsolationError):
        audit_citations(fixture.claim, [smuggled])
