"""Offline claim decomposition. Fixtures stay deterministic and do not call a model."""

from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from validator.decompose import (
    CLAIM_BUDGET,
    DecomposeError,
    DecomposeInput,
    LiveDecompositionRefused,
    decompose,
    load_fixture,
    main,
    neutral_reader_input,
)
from validator.evidence_reader import assert_reader_boundary
from validator.schemas import Claim

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "decompose"
SCHEMA = json.loads((ROOT / "schemas" / "mavs_claim_record.schema.json").read_text(encoding="utf-8"))
VALIDATOR = Draft202012Validator(SCHEMA)
_CAUSAL = ("cause", "caused", "causes", "causal", "causation")


def _run(name: str):
    spec = load_fixture(FIXTURES / name)
    return spec, decompose(spec)


def _assert_schema(claims: list[Claim]) -> None:
    assert claims
    for claim in claims:
        errors = sorted(error.message for error in VALIDATOR.iter_errors(claim.model_dump(mode="json")))
        assert errors == []
        assert claim.neutral_question
        assert claim.asserted_answer
        assert claim.exact_source_span
        assert claim.asserted_answer == claim.normalized_claim
        assert claim.asserted_answer not in claim.neutral_question


def _assert_spans(spec: DecomposeInput, claims: list[Claim]) -> None:
    for claim in claims:
        assert claim.exact_source_span in spec.frozen_conclusion
        if spec.report_text is not None:
            assert claim.exact_source_span in spec.report_text
        assert claim.report_id == spec.report_id
        assert claim.source.dataset == "scifact"
        assert claim.source.native_id == spec.native_id


def _no_causal(text: str) -> bool:
    folded = text.casefold()
    return all(token not in folded.split() and f" {token} " not in f" {folded} " for token in _CAUSAL)


def test_conjunction_splits_effects_and_keeps_the_dependency():
    spec, result = _run("conjunction.json")
    _assert_schema(result.claims)
    _assert_spans(spec, result.claims)
    assert result.partial is False
    assert result.unchecked_spans == []
    assert len(result.claims) == 2
    memory, anxiety = result.claims
    assert memory.dependencies == []
    assert anxiety.dependencies == [memory.claim_id]
    assert "memory retention" in (memory.object or "")
    assert "anxiety" in (anxiety.object or "")
    assert "memory retention" not in (anxiety.object or "")
    for claim in result.claims:
        assert claim.population is not None and claim.population.casefold() == "mice"
        assert "in mice" in claim.normalized_claim.casefold()
        assert claim.comparator is not None and "vehicle" in claim.comparator.casefold()
        assert "compared with" in claim.normalized_claim.casefold()
        assert claim.modality == "effect"
        assert "improves" not in claim.neutral_question.casefold()
        assert "reduces" not in claim.neutral_question.casefold()
        assert claim.relation is not None
        assert claim.relation.casefold() not in claim.neutral_question.casefold()
    assert memory.relation is not None and memory.relation.casefold() == "improves"
    assert anxiety.relation is not None and anxiety.relation.casefold() == "reduces"
    assert memory.exact_source_span == anxiety.exact_source_span


def test_population_qualifiers_stay_on_their_own_claims():
    spec, result = _run("population.json")
    _assert_schema(result.claims)
    _assert_spans(spec, result.claims)
    assert len(result.claims) == 2
    mice, adults = result.claims
    assert mice.population is not None and mice.population.casefold() == "mice"
    assert "in mice" in mice.normalized_claim.casefold()
    assert "older adults" not in mice.normalized_claim.casefold()
    assert adults.population is not None and adults.population.casefold() == "older adults"
    assert "older adults" in adults.normalized_claim.casefold()
    assert "mice" not in adults.normalized_claim.casefold()
    assert "the same compound" in adults.normalized_claim
    assert adults.modality == "association"
    assert adults.relation is not None and "associated" in adults.relation.casefold()
    assert "cause" not in adults.relation.casefold()
    assert "causal" not in (adults.modality or "")
    assert _no_causal(adults.normalized_claim)
    assert _no_causal(adults.neutral_question or "")
    assert mice.dependencies == []
    assert adults.dependencies == []


def test_numeric_effect_size_percent_hedge_and_setting_are_kept():
    spec, result = _run("numeric.json")
    _assert_schema(result.claims)
    _assert_spans(spec, result.claims)
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert "12.5%" in claim.normalized_claim
    assert "12.5%" in (claim.asserted_answer or "")
    assert "effect size of 0.42" in claim.normalized_claim
    assert "0.42" in (claim.asserted_answer or "")
    assert claim.units == "%"
    assert "may" in claim.normalized_claim.casefold()
    assert claim.modality == "hedged_effect"
    assert claim.population is not None and claim.population.casefold() == "older adults"
    assert "older adults" in claim.normalized_claim.casefold()
    assert claim.comparator is not None and "placebo" in claim.comparator.casefold()
    assert "compared with" in claim.normalized_claim.casefold()
    assert "randomized trial" in claim.normalized_claim.casefold()
    assert "may" not in (claim.neutral_question or "").casefold()
    assert "lower" not in (claim.neutral_question or "").casefold()
    assert claim.dependencies == []


def test_associated_with_stays_association():
    spec, result = _run("association.json")
    _assert_schema(result.claims)
    _assert_spans(spec, result.claims)
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.modality == "association"
    assert claim.relation is not None
    assert "associated" in claim.relation.casefold()
    assert claim.relation.casefold() != "causes"
    for token in _CAUSAL:
        assert token not in claim.relation.casefold().split()
        assert token not in (claim.modality or "").casefold().split()
        assert token not in claim.normalized_claim.casefold().split()
        assert token not in (claim.neutral_question or "").casefold().split()
    assert "in mice" in claim.normalized_claim.casefold()
    assert claim.population is not None and "mice" in claim.population.casefold()
    assert "lower tumor volume" in claim.normalized_claim.casefold()
    assert claim.comparator is not None and "vehicle" in claim.comparator.casefold()
    assert "compared with" in claim.normalized_claim.casefold()
    assert "association" in (claim.neutral_question or "").casefold()


def test_opinions_and_recommendations_are_separate_claims():
    spec, result = _run("recommendation.json")
    _assert_schema(result.claims)
    _assert_spans(spec, result.claims)
    by_modality = {claim.modality: claim for claim in result.claims}
    assert set(by_modality) == {"effect", "opinion", "recommendation"}
    effect = by_modality["effect"]
    opinion = by_modality["opinion"]
    recommendation = by_modality["recommendation"]
    assert "20%" in effect.normalized_claim
    assert "20%" in (effect.asserted_answer or "")
    assert effect.units == "%"
    assert effect.population is not None and "older adults" in effect.population.casefold()
    assert "20%" not in opinion.normalized_claim
    assert "20%" not in recommendation.normalized_claim
    assert "in our opinion" in opinion.normalized_claim.casefold()
    assert "promising" in opinion.normalized_claim.casefold()
    assert "in our opinion" not in (opinion.neutral_question or "").casefold()
    assert "promising" in (opinion.neutral_question or "").casefold()
    assert recommendation.relation == "recommend"
    assert "we recommend" in recommendation.normalized_claim.casefold()
    assert "we recommend" not in (recommendation.neutral_question or "").casefold()
    assert recommendation.population is not None and "older adults" in recommendation.population.casefold()
    assert effect.dependencies == []
    assert opinion.dependencies == []
    assert recommendation.dependencies == []


def test_reader_input_never_carries_the_asserted_answer():
    for name in (
        "conjunction.json",
        "population.json",
        "numeric.json",
        "association.json",
        "recommendation.json",
    ):
        _, result = _run(name)
        for claim in result.claims:
            payload = neutral_reader_input(claim)
            assert set(payload) == {"neutral_question"}
            blob = json.dumps(payload)
            assert "asserted_answer" not in payload
            assert "asserted_answer" not in blob
            assert claim.asserted_answer not in blob
            assert claim.normalized_claim not in blob
            assert_reader_boundary({**payload, "passages": []})


def test_object_coordination_keeps_association_and_shared_scope():
    spec = DecomposeInput(
        frozen_conclusion=(
            "In older adults, vitamin D was associated with higher bone density "
            "and lower fracture risk compared with placebo."
        ),
        native_id=910011,
        report_id="decompose-association-split",
        split_role="development",
    )
    result = decompose(spec)
    _assert_schema(result.claims)
    assert len(result.claims) == 2
    density, fracture = result.claims
    assert fracture.dependencies == [density.claim_id]
    for claim in result.claims:
        assert claim.modality == "association"
        assert claim.relation is not None and "associated" in claim.relation.casefold()
        assert claim.population is not None and claim.population.casefold() == "older adults"
        assert "older adults" in claim.normalized_claim.casefold()
        assert claim.comparator is not None and "placebo" in claim.comparator.casefold()
        assert _no_causal(claim.normalized_claim)
        assert "causal" not in (claim.modality or "")
    assert "higher bone density" in density.normalized_claim.casefold()
    assert "lower fracture risk" not in density.normalized_claim.casefold()
    assert "lower fracture risk" in fracture.normalized_claim.casefold()
    assert "higher bone density" not in fracture.normalized_claim.casefold()


def test_per_conjunct_populations_are_not_swapped_or_upgraded():
    spec = DecomposeInput(
        frozen_conclusion=(
            "Compound MX-42 reduced amyloid burden in mice and was associated "
            "with slower decline in older adults."
        ),
        native_id=910012,
        report_id="decompose-population-split",
    )
    result = decompose(spec)
    _assert_schema(result.claims)
    mice, adults = result.claims
    assert adults.dependencies == [mice.claim_id]
    assert mice.modality == "effect"
    assert mice.population is not None and mice.population.casefold() == "mice"
    assert "older adults" not in mice.normalized_claim.casefold()
    assert adults.modality == "association"
    assert adults.population is not None and adults.population.casefold() == "older adults"
    assert "mice" not in adults.normalized_claim.casefold()
    assert _no_causal(adults.normalized_claim)
    assert "associated" in (adults.relation or "").casefold()


def test_quantities_stay_on_the_conjunct_that_stated_them():
    spec = DecomposeInput(
        frozen_conclusion=(
            "Compound MX-42 improves memory retention by 25% and reduces anxiety "
            "by 10% in mice compared with vehicle."
        ),
        native_id=910013,
        report_id="decompose-quantities",
    )
    result = decompose(spec)
    memory, anxiety = result.claims
    assert "25%" in memory.normalized_claim
    assert "10%" not in memory.normalized_claim
    assert "10%" in anxiety.normalized_claim
    assert "25%" not in anxiety.normalized_claim
    assert "25%" in (memory.asserted_answer or "")
    assert "10%" in (anxiety.asserted_answer or "")
    for claim in result.claims:
        assert "in mice" in claim.normalized_claim.casefold()
        assert "vehicle" in (claim.comparator or "").casefold()
    assert anxiety.dependencies == [memory.claim_id]


def test_explicit_causal_scope_is_preserved():
    spec = DecomposeInput(
        frozen_conclusion="Compound MX-42 causes weight loss in mice compared with vehicle.",
        native_id=910014,
        report_id="decompose-causal",
    )
    result = decompose(spec)
    claim = result.claims[0]
    assert claim.modality == "causal"
    assert claim.relation is not None and claim.relation.casefold() == "causes"
    assert "causes" in claim.normalized_claim.casefold()
    assert "in mice" in claim.normalized_claim.casefold()
    assert "vehicle" in (claim.comparator or "").casefold()
    assert "associated" not in (claim.relation or "").casefold()


def test_time_phrase_is_kept():
    spec = DecomposeInput(
        frozen_conclusion="Compound MX-42 reduced pain after 12 weeks in mice compared with vehicle.",
        native_id=910015,
        report_id="decompose-time",
    )
    claim = decompose(spec).claims[0]
    assert claim.time is not None and "12 weeks" in claim.time
    assert "after 12 weeks" in claim.normalized_claim.casefold()
    assert "in mice" in claim.normalized_claim.casefold()


def test_default_budget_lists_the_unchecked_span():
    sentences = [f"Compound MX-{index} improves memory in mice." for index in range(1, 10)]
    spec = DecomposeInput(
        frozen_conclusion=" ".join(sentences),
        native_id=910016,
        report_id="decompose-budget",
    )
    result = decompose(spec)
    assert CLAIM_BUDGET == 8
    assert result.partial is True
    assert len(result.claims) == 8
    assert result.unchecked_spans == ["Compound MX-9 improves memory in mice."]
    assert result.unchecked_spans[0] in spec.frozen_conclusion
    assert result.unchecked_spans[0] not in {claim.exact_source_span for claim in result.claims}
    _assert_schema(result.claims)


def test_claim_budget_cannot_exceed_the_research_plan_cap():
    spec = DecomposeInput(frozen_conclusion="Compound MX-42 improves memory in mice.", native_id=1)
    with pytest.raises(DecomposeError):
        decompose(spec, claim_budget=0)
    with pytest.raises(DecomposeError):
        decompose(spec, claim_budget=9)


def test_live_decomposition_is_refused_without_a_socket(monkeypatch: pytest.MonkeyPatch):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("decompose opened a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    spec = DecomposeInput(frozen_conclusion="Compound MX-42 improves memory in mice.", native_id=1)
    with pytest.raises(LiveDecompositionRefused):
        decompose(spec, dry_run=False)


def test_cli_writes_schema_valid_claims(tmp_path: Path):
    output = tmp_path / "claims.json"
    assert main(["--fixture", str(FIXTURES / "conjunction.json"), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["dry_run"] is True
    assert payload["partial"] is False
    assert len(payload["claims"]) == 2
    assert payload["claims"][1]["dependencies"] == [payload["claims"][0]["claim_id"]]
    for claim in payload["claims"]:
        assert list(VALIDATOR.iter_errors(claim)) == []
        assert "asserted_answer" in claim
        assert claim["asserted_answer"]


def test_cli_live_flag_refuses_before_writing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("decompose opened a network connection")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    output = tmp_path / "claims.json"
    assert main(["--fixture", str(FIXTURES / "association.json"), "--live", "--output", str(output)]) == 2
    assert not output.exists()


def test_cli_conclusion_mode_and_help(capsys: pytest.CaptureFixture[str]):
    assert (
        main(
            [
                "--conclusion",
                "In mice, higher MX-42 exposure was associated with lower tumor volume.",
                "--native-id",
                "910020",
                "--report-id",
                "cli-association",
                "--dry-run",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["claims"][0]["modality"] == "association"
    assert "cause" not in payload["claims"][0]["relation"]
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    help_text = capsys.readouterr().out
    assert "deterministic" in help_text.casefold()
    assert "BM25" in help_text
    assert "--live" in help_text


def test_module_does_not_wire_retrieval_or_a_model():
    text = (ROOT / "src" / "validator" / "decompose.py").read_text(encoding="utf-8")
    assert "validator.retrieve" not in text
    assert "retrieval.bm25" not in text
    assert "inference_client" not in text
    assert "fixture_pipeline" not in text
    assert "urllib" not in text
    assert "lmstudio" not in text.casefold()
