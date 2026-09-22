"""Fixture run of the staged judge: happy path, missing citation, four-way policy."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from validator.evidence_reader import compute_seal
from validator.fixture_pipeline import StagedVerdict, load_fixture, main, run_fixture
from validator.label_policy import PassageView, decide_label
from validator.render import ClaimCard, RenderError, verify_explanations
from validator.schemas import EvidenceScope, ExecutionStatus, LabelSpace, ScientificLabel

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "judgment"
COMPLETE = FIXTURES / "complete.json"
MISSING = FIXTURES / "missing_citation.json"
COMPLETE_VERDICT = FIXTURES / "complete_verdict.json"
MISSING_VERDICT = FIXTURES / "missing_citation_verdict.json"
LEAK = "LEAK_ASSERTED_ANSWER"
PINNED_CORPUS_HASH = "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62"
FOUR_WAY = {item.value for item in ScientificLabel}


def test_label_policy_covers_the_four_labels():
    claim = "In the mouse model, compound MX-42 increased memory retention."
    support = PassageView(
        span_id="D1:1:0-10",
        text=(
            "In the mouse model, compound MX-42 increased memory retention "
            "compared with vehicle."
        ),
    )
    contradict = PassageView(
        span_id="D1:2:0-10",
        text=(
            "In the mouse model, compound MX-42 decreased memory retention "
            "compared with vehicle."
        ),
    )
    negated = PassageView(
        span_id="D1:3:0-10",
        text=(
            "In the mouse model, compound MX-42 did not increase memory retention "
            "compared with vehicle."
        ),
    )
    unrelated = PassageView(
        span_id="D1:4:0-10",
        text="A separate yeast assay reported unchanged glucose uptake under solvent control.",
    )
    causal = "Compound MX-42 caused increased memory retention in the mouse model."

    supported = decide_label(claim, [support, unrelated])
    assert supported.label is ScientificLabel.SUPPORTED
    assert supported.cited_span_ids == ["D1:1:0-10"]

    contradicted = decide_label(claim, [contradict])
    assert contradicted.label is ScientificLabel.CONTRADICTED
    assert decide_label(claim, [negated]).label is ScientificLabel.CONTRADICTED

    unaddressed = decide_label(claim, [unrelated])
    assert unaddressed.label is ScientificLabel.UNADDRESSED
    assert unaddressed.cited_span_ids == []

    measured = PassageView(
        span_id="D1:5:0-10",
        text="In the mouse model, compound MX-42 memory retention was measured.",
    )
    inconclusive = decide_label(claim, [measured])
    assert inconclusive.label is ScientificLabel.UNDERDETERMINED
    assert "inconclusive_relevant_evidence" in inconclusive.rationale_codes

    conflict = decide_label(claim, [support, contradict])
    assert conflict.label is ScientificLabel.UNDERDETERMINED
    assert "conflicting_results" in conflict.rationale_codes

    overreach = decide_label(causal, [support])
    assert overreach.label is ScientificLabel.UNDERDETERMINED
    assert "causal_overreach" in overreach.rationale_codes


def test_complete_fixture_bundle_uses_locked_corpus_hash():
    corpus = yaml.safe_load((ROOT / "configs" / "corpus" / "scifact.yaml").read_text(encoding="utf-8"))
    fixture = load_fixture(COMPLETE)
    assert fixture.d1_bundle.corpus_hash == corpus["corpus_hash"] == PINNED_CORPUS_HASH
    assert fixture.claim.claim_id == "scifact:900042"
    assert fixture.d0_evidence
    assert all(item.access_scope.value == "D0" for item in fixture.d0_evidence)
    assert all(item.provenance is not None and item.provenance.value == "original" for item in fixture.d0_evidence)
    assert all(item.access_scope.value == "D1" for item in fixture.d1_bundle.passages)
    assert all(
        item.provenance is not None and item.provenance.value == "independent"
        for item in fixture.d1_bundle.passages
    )


def test_reader_seals_before_the_judge_sees_the_claim(monkeypatch: pytest.MonkeyPatch):
    import validator.fixture_pipeline as pipeline

    events: list[str] = []
    real_read = pipeline.read_evidence
    real_judge = pipeline.judge_claim

    def wrapped_read(payload):
        events.append("read")
        assert "asserted_answer" not in payload
        assert LEAK not in json.dumps(payload)
        return real_read(payload)

    def wrapped_judge(claim, sealed, bundle):
        events.append("judge")
        assert events == ["read", "judge"]
        assert sealed.seal == compute_seal(
            sealed.neutral_question, sealed.answer, sealed.cited_span_ids
        )
        assert LEAK not in sealed.answer
        return real_judge(claim, sealed, bundle)

    monkeypatch.setattr(pipeline, "read_evidence", wrapped_read)
    monkeypatch.setattr(pipeline, "judge_claim", wrapped_judge)
    verdict = pipeline.run_fixture(load_fixture(COMPLETE))
    assert events == ["read", "judge"]
    assert verdict.sealed_reader.seal


def test_complete_fixture_emits_four_way_verdict():
    verdict = run_fixture(load_fixture(COMPLETE))
    assert len(verdict.judgments) == 2
    by_scope = {item.evidence_scope: item for item in verdict.judgments}
    d1 = by_scope[EvidenceScope.D1]
    d0 = by_scope[EvidenceScope.D0]
    assert d1.label_space is LabelSpace.MAVS_FOUR_WAY
    assert d0.label_space is LabelSpace.MAVS_FOUR_WAY
    assert d1.label in FOUR_WAY
    assert d0.label in FOUR_WAY
    assert d1.label == ScientificLabel.SUPPORTED.value
    assert d0.label == ScientificLabel.SUPPORTED.value
    assert d1.execution_status is ExecutionStatus.COMPLETED
    assert d0.execution_status is ExecutionStatus.COMPLETED
    assert d1.label not in {item.value for item in ExecutionStatus}
    assert d1.cited_span_ids
    assert verdict.citation_flags
    assert verdict.citation_flags[0].adequacy == "adequate"
    assert verdict.reconciler_notes
    report = verdict.report_verdict
    assert report.claim_coverage["claims_judged"] == 1
    assert report.central_claim_outcomes[0]["agreed_label"] == "supported"
    assert report.inference_link_status[0]["status"] == "valid"
    assert report.conflicts_d0_d1 == []
    assert report.display_explanation
    assert report.limitations
    assert "Live model prompts" in " ".join(report.limitations)
    assert LEAK not in verdict.model_dump_json()
    committed = json.loads(COMPLETE_VERDICT.read_text(encoding="utf-8"))
    assert json.loads(verdict.model_dump_json()) == committed
    assert StagedVerdict.model_validate(committed).sealed_reader.seal == verdict.sealed_reader.seal


def test_missing_citation_fixture_keeps_structured_failure():
    verdict = run_fixture(load_fixture(MISSING))
    by_scope = {item.evidence_scope: item for item in verdict.judgments}
    d1 = by_scope[EvidenceScope.D1]
    d0 = by_scope[EvidenceScope.D0]
    assert d1.label == ScientificLabel.SUPPORTED.value
    assert d1.execution_status is ExecutionStatus.COMPLETED
    assert d0.label == ScientificLabel.UNADDRESSED.value
    assert d0.execution_status is ExecutionStatus.FAILED
    assert d0.label != d1.label
    assert verdict.citation_flags[0].adequacy == "inadequate"
    assert "missing_required_citation" in verdict.citation_flags[0].defects
    assert verdict.report_verdict.conflicts_d0_d1
    assert verdict.report_verdict.inference_link_status[0]["status"] == "unresolved"
    assert verdict.reconciler_notes
    assert verdict.claim_card.original_citations == "inadequate"
    assert "D1 was not used to repair D0" in " ".join(verdict.report_verdict.limitations)
    assert LEAK not in verdict.model_dump_json()
    committed = json.loads(MISSING_VERDICT.read_text(encoding="utf-8"))
    assert json.loads(verdict.model_dump_json()) == committed
    assert StagedVerdict.model_validate(committed).judgments


def test_cli_writes_verdict_json(tmp_path: Path):
    output = tmp_path / "verdict.json"
    assert main(["--fixture", str(COMPLETE), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["judgments"][0]["label"] == "supported"
    assert payload["citation_flags"]
    assert payload["reconciler_notes"]
    assert payload["report_verdict"]["display_explanation"]


def test_renderer_rejects_an_explanatory_sentence_without_a_span():
    card = ClaimCard(
        claim="In the mouse model, compound MX-42 increased memory retention.",
        evidence_verdict="Evidence verdict: supported.",
        why=["Why: the study showed a benefit."],
        what_is_uncertain="None recorded.",
        search_scope="corpus hash abc; 1 independent passages; retrieval round 1.",
        original_citations="adequate",
        next_useful_check="No further check is recorded on this claim.",
        display_text="Why: the study showed a benefit.",
    )
    with pytest.raises(RenderError):
        verify_explanations(card, {"D1:880042:0-1"})


def test_judgment_modules_do_not_call_the_retriever():
    root = ROOT / "src" / "validator"
    names = [
        "label_policy.py",
        "evidence_reader.py",
        "judge.py",
        "citation_auditor.py",
        "reconcile.py",
        "render.py",
        "fixture_pipeline.py",
    ]
    for name in names:
        text = (root / name).read_text(encoding="utf-8")
        assert "validator.retrieve" not in text
        assert "retrieval.bm25" not in text
        assert "vllm" not in text.casefold()
