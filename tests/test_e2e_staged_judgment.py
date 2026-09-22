"""Offline D0 ∪ D1 staged judgment: decompose or fixture claims through the report runner."""

from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from validator.citation_auditor import audit_citations
from validator.evidence_reader import IsolationError, compute_seal
from validator.fixture_pipeline import (
    JUDGE_PASSAGE_BUDGET,
    ClaimAttachment,
    PipelineError,
    cap_evidence_bundle,
    load_fixture,
    load_report_fixture,
    main,
    run_fixture,
    run_report,
)
from validator.retrieval.models import PASSAGE_CEILING
from validator.runner import main as runner_main
from validator.runner import neutral_gather_text
from validator.schemas import Evidence, EvidenceScope, ExecutionStatus, ScientificLabel

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "judgment"
HAPPY = FIXTURES / "e2e_happy.json"
CONFLICT = FIXTURES / "e2e_conflict.json"
MISSING = FIXTURES / "e2e_missing_citation.json"
COMPLETE = FIXTURES / "complete.json"
LEAK = "LEAK_ASSERTED_ANSWER"
FOUR_WAY = {item.value for item in ScientificLabel}


def _validator(name: str) -> Draft202012Validator:
    schema = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args, **_kwargs):
        raise AssertionError("e2e fixture path opened a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)


def test_happy_path_emits_d0_d1_and_reconciled_views(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    verdict = run_report(load_report_fixture(HAPPY))
    assert verdict.dry_run is True
    assert verdict.partial is False
    assert verdict.claims_judged == 1
    assert verdict.claims_in_report == 1
    assert verdict.report_id == "e2e-happy"
    claim = verdict.claims[0]
    assert claim.proposer_claim_id == "agentic:e2e-happy:1"
    assert claim.claim_id == "scifact:900042"
    assert claim.d0.evidence_scope is EvidenceScope.D0
    assert claim.d1.evidence_scope is EvidenceScope.D1
    assert claim.reconciled.evidence_scope is EvidenceScope.D0_UNION_D1
    assert claim.d0.label == ScientificLabel.SUPPORTED.value
    assert claim.d1.label == ScientificLabel.SUPPORTED.value
    assert claim.reconciled.label == ScientificLabel.SUPPORTED.value
    assert claim.d0.execution_status is ExecutionStatus.COMPLETED
    assert claim.d1.execution_status is ExecutionStatus.COMPLETED
    assert claim.reconciled.execution_status is ExecutionStatus.COMPLETED
    assert claim.d0.label in FOUR_WAY
    assert claim.reconciled.rationale_codes == ["labels_agree"]
    assert claim.sealed_reader.seal == compute_seal(
        claim.sealed_reader.neutral_question,
        claim.sealed_reader.answer,
        claim.sealed_reader.cited_span_ids,
    )
    assert claim.claim_card.display_text
    assert claim.claim_card.original_citations == "adequate"
    assert claim.claim_card.claim
    assert verdict.report_verdict.display_explanation == claim.claim_card.display_text
    assert verdict.report_verdict.conflicts_d0_d1 == []
    assert "not repaired or replaced" in " ".join(verdict.report_verdict.limitations)
    label_schema = _validator("mavs_label_record.schema.json")
    report_schema = _validator("mavs_report_verdict.schema.json")
    for judgment in (claim.d0, claim.d1, claim.reconciled):
        assert list(label_schema.iter_errors(judgment.model_dump(mode="json"))) == []
    assert list(report_schema.iter_errors(verdict.report_verdict.model_dump(mode="json"))) == []


def test_conflict_keeps_the_d0_label(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    fixture = load_report_fixture(CONFLICT)
    verdict = run_report(fixture)
    claim = verdict.claims[0]
    fresh = audit_citations(fixture.claims[0], fixture.attachments[0].d0_evidence)
    assert claim.d0.model_dump() == fresh.judgment.model_dump()
    assert claim.d0.label == ScientificLabel.SUPPORTED.value
    assert claim.d1.label == ScientificLabel.CONTRADICTED.value
    assert claim.reconciled.label == ScientificLabel.UNDERDETERMINED.value
    assert claim.reconciled.label != claim.d1.label
    assert claim.d0.evidence_scope is EvidenceScope.D0
    assert claim.reconciled.evidence_scope is EvidenceScope.D0_UNION_D1
    assert claim.d0.label == ScientificLabel.SUPPORTED.value
    notes = " ".join(note.note for note in claim.reconciler_notes)
    assert "not used to repair" in notes
    assert verdict.report_verdict.conflicts_d0_d1
    assert verdict.report_verdict.conflicts_d0_d1[0]["d0_label"] == "supported"
    assert verdict.report_verdict.conflicts_d0_d1[0]["d1_label"] == "contradicted"
    assert claim.claim_card.original_citations == "adequate"
    assert LEAK not in verdict.model_dump_json()


def test_missing_citation_is_not_repaired_from_d1(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    verdict = run_report(load_report_fixture(MISSING))
    claim = verdict.claims[0]
    assert claim.d0.label == ScientificLabel.UNADDRESSED.value
    assert claim.d0.execution_status is ExecutionStatus.FAILED
    assert claim.d1.label == ScientificLabel.SUPPORTED.value
    assert claim.d1.execution_status is ExecutionStatus.COMPLETED
    assert claim.reconciled.label == ScientificLabel.UNDERDETERMINED.value
    assert claim.reconciled.label != claim.d1.label
    assert "d0_not_repaired_from_d1" in claim.reconciled.rationale_codes
    assert claim.reconciled.execution_status is ExecutionStatus.FAILED
    assert claim.claim_card.original_citations == "inadequate"
    assert "D1 was not used to repair D0" in " ".join(verdict.report_verdict.limitations)
    assert verdict.report_verdict.conflicts_d0_d1


def test_reader_stays_blind_on_the_report_path(monkeypatch: pytest.MonkeyPatch):
    import validator.fixture_pipeline as pipeline

    events: list[str] = []
    real_read = pipeline.read_evidence
    real_judge = pipeline.judge_claim

    def wrapped_read(payload):
        events.append("read")
        assert set(payload) == {"neutral_question", "passages"}
        assert "asserted_answer" not in payload
        blob = json.dumps(payload)
        assert LEAK not in blob
        # The proposer stores the frozen sentence as asserted_answer. That
        # sentence is not a reader field. Passage text may share words.
        frozen = "In the mouse model, compound MX-42 increased memory retention."
        assert frozen not in blob
        return real_read(payload)

    def wrapped_judge(claim, sealed, bundle):
        events.append("judge")
        assert events[-2:] == ["read", "judge"]
        assert sealed.seal == compute_seal(
            sealed.neutral_question, sealed.answer, sealed.cited_span_ids
        )
        assert LEAK not in sealed.answer
        return real_judge(claim, sealed, bundle)

    monkeypatch.setattr(pipeline, "read_evidence", wrapped_read)
    monkeypatch.setattr(pipeline, "judge_claim", wrapped_judge)
    happy = run_report(load_report_fixture(HAPPY))
    conflict = run_report(load_report_fixture(CONFLICT))
    assert events == ["read", "judge", "read", "judge"]
    assert LEAK not in happy.model_dump_json()
    assert LEAK not in conflict.model_dump_json()
    assert happy.claims[0].sealed_reader.seal


def test_auditor_rejects_d1_passed_as_d0():
    fixture = load_report_fixture(HAPPY)
    passage = fixture.attachments[0].d1_bundle.passages[0]
    smuggled = Evidence.model_validate(passage.model_dump(exclude={"score"}))
    broken = fixture.model_copy(
        update={
            "attachments": [
                fixture.attachments[0].model_copy(update={"d0_evidence": [smuggled]})
            ]
        }
    )
    with pytest.raises(IsolationError):
        run_report(broken)


def test_dry_run_does_not_call_gather(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)

    def boom(_claim):
        raise AssertionError("dry_run called gather")

    verdict = run_report(load_report_fixture(HAPPY), gather_fn=boom, dry_run=True)
    assert verdict.claims[0].d1.label == ScientificLabel.SUPPORTED.value
    with pytest.raises(PipelineError, match="refuses live gather"):
        run_report(load_report_fixture(HAPPY), gather_fn=boom, dry_run=False)


def test_gather_stub_sees_the_neutral_question_only():
    base = load_report_fixture(HAPPY)
    opened = base.model_copy(update={"dry_run": False})
    attachment = opened.attachments[0].model_copy(update={"d1_bundle": None})
    fixture = opened.model_copy(update={"attachments": [attachment]})
    bundle = base.attachments[0].d1_bundle
    assert bundle is not None
    seen: list[str] = []

    def gather_fn(claim):
        text = neutral_gather_text(claim)
        seen.append(text)
        assert claim.asserted_answer not in text
        assert "asserted_answer" not in text
        return bundle.model_copy(update={"claim_id": claim.claim_id})

    verdict = run_report(fixture, gather_fn=gather_fn, dry_run=False)
    assert len(seen) == 1
    assert seen[0].startswith("What did")
    assert "increased memory retention." not in seen[0]
    assert verdict.claims[0].claim_id == "scifact:900042"
    assert verdict.claims[0].d1.label == ScientificLabel.SUPPORTED.value
    assert verdict.dry_run is False
    assert "opt-in gather path" in " ".join(verdict.report_verdict.limitations)


def test_missing_bundle_on_dry_run_refuses_gather():
    base = load_report_fixture(CONFLICT)
    attachment = base.attachments[0].model_copy(update={"d1_bundle": None})
    fixture = base.model_copy(update={"attachments": [attachment]})

    def boom(_claim):
        raise AssertionError("dry_run called gather")

    with pytest.raises(PipelineError, match="does not call gather"):
        run_report(fixture, gather_fn=boom)


def test_claim_budget_marks_partial_coverage(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    conflict = load_report_fixture(CONFLICT)
    base_claim = conflict.claims[0]
    base_attachment = conflict.attachments[0]
    claims = []
    attachments: list[ClaimAttachment] = []
    for index in range(9):
        claim_id = f"scifact:{910000 + index}"
        claims.append(
            base_claim.model_copy(
                update={
                    "claim_id": claim_id,
                    "report_id": "e2e-budget",
                    "exact_source_span": (
                        f"Span {index} for compound MX-42 and memory retention."
                    ),
                    "source": base_claim.source.model_copy(update={"native_id": 910000 + index}),
                }
            )
        )
        bundle = base_attachment.d1_bundle.model_copy(update={"claim_id": claim_id})
        attachments.append(
            base_attachment.model_copy(
                update={"retrieval_claim_id": claim_id, "d1_bundle": bundle}
            )
        )
    fixture = conflict.model_copy(
        update={"fixture_id": "e2e-budget", "claims": claims, "attachments": attachments}
    )
    verdict = run_report(fixture)
    assert JUDGE_PASSAGE_BUDGET == PASSAGE_CEILING == 8
    assert verdict.partial is True
    assert verdict.claims_judged == 8
    assert verdict.claims_in_report == 9
    assert verdict.unchecked_spans == [claims[8].exact_source_span]
    coverage = verdict.report_verdict.claim_coverage
    assert coverage["partial"] is True
    assert coverage["claims_judged"] == 8
    assert claims[8].claim_id not in coverage["claim_ids"]
    assert "budget" in " ".join(verdict.report_verdict.limitations).casefold()


def test_decompose_budget_lists_the_unchecked_sentence():
    happy = load_report_fixture(HAPPY)
    spec = happy.decompose.model_copy(
        update={
            "frozen_conclusion": (
                "In the mouse model, compound MX-42 increased memory retention. "
                "Compound MX-9 improves memory in mice."
            )
        }
    )
    fixture = happy.model_copy(update={"decompose": spec})
    verdict = run_report(fixture, claim_budget=1)
    assert verdict.partial is True
    assert verdict.claims_judged == 1
    assert verdict.claims[0].d0.label == ScientificLabel.SUPPORTED.value
    assert any("MX-9" in span for span in verdict.unchecked_spans)
    with pytest.raises(PipelineError):
        run_report(fixture, claim_budget=9)


def test_passage_budget_drops_extra_passages_before_the_reader(monkeypatch: pytest.MonkeyPatch):
    import validator.fixture_pipeline as pipeline

    seen: list[dict] = []
    real_read = pipeline.read_evidence

    def wrapped(payload):
        seen.append(payload)
        return real_read(payload)

    monkeypatch.setattr(pipeline, "read_evidence", wrapped)
    verdict = run_fixture(load_fixture(COMPLETE), passage_budget=1)
    assert len(seen) == 1
    assert len(seen[0]["passages"]) == 1
    assert "yeast" not in json.dumps(seen[0])
    assert verdict.judgments[0].label == ScientificLabel.SUPPORTED.value
    bundle = load_fixture(COMPLETE).d1_bundle
    assert cap_evidence_bundle(bundle) is bundle
    with pytest.raises(PipelineError):
        cap_evidence_bundle(bundle, limit=9)
    capped = cap_evidence_bundle(bundle, limit=1)
    assert len(capped.passages) == 1
    assert capped.passages[0].rank == 1


def test_cli_dry_run_writes_the_report_verdict(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    output = tmp_path / "verdict.json"
    assert main(["--fixture", str(HAPPY), "--dry-run", "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    claim = payload["claims"][0]
    assert claim["d0"]["label"] == "supported"
    assert claim["d1"]["label"] == "supported"
    assert claim["reconciled"]["evidence_scope"] == "D0_union_D1"
    assert claim["reconciled"]["label"] == "supported"
    assert claim["claim_card"]["display_text"]
    assert runner_main(["--fixture", str(HAPPY), "--output", str(tmp_path / "runner.json")]) == 0
    runner_payload = json.loads((tmp_path / "runner.json").read_text(encoding="utf-8"))
    assert runner_payload["claims"][0]["d0"]["label"] == "supported"


def test_runner_gather_flag_is_refused_for_a_dry_fixture(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    assert runner_main(["--fixture", str(HAPPY), "--gather"]) == 2
    with pytest.raises(SystemExit) as exc:
        runner_main(["--fixture", str(HAPPY), "--dry-run", "--gather"])
    assert exc.value.code == 2


def test_judgment_modules_still_do_not_call_the_retriever():
    text = (ROOT / "src" / "validator" / "fixture_pipeline.py").read_text(encoding="utf-8")
    assert "validator.retrieve" not in text
    assert "retrieval.bm25" not in text
    runner = (ROOT / "src" / "validator" / "runner.py").read_text(encoding="utf-8")
    assert "neutral_gather_text(claim)" in runner
    assert "gather(neutral_gather_text(claim), config, claim.claim_id)" in runner


def test_neutral_gather_text_rejects_a_leaking_question():
    fixture = load_report_fixture(CONFLICT)
    claim = fixture.claims[0]
    assert LEAK in (claim.asserted_answer or "")
    assert LEAK not in neutral_gather_text(claim)
    leaked = claim.model_copy(
        update={"neutral_question": f"What about {claim.asserted_answer}?"}
    )
    with pytest.raises(IsolationError):
        neutral_gather_text(leaked)
