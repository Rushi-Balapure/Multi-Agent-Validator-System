"""V versus B2 false-endorsement harness.

Empty V must stay pending. The live B2 column is read from the checked-in
metrics report. When V dry-run predictions exist, the paper table keeps that
B2 column and fills V from ``score_predictions`` (fixture-report smoke gold
for synthetic e2e claim ids).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from evaluation.harness import (
    EM_DASH,
    FORMULA_ID,
    HELD_OUT_B2_RUN_ID_PLACEHOLDER,
    HELD_OUT_V_RUN_ID_PLACEHOLDER,
    PENDING,
    V_RUN_ID_PLACEHOLDER,
    CompareError,
    compare_false_endorsement,
    compare_live_b2,
    main,
    render_comparison_markdown,
    render_live_stub_markdown,
    score_from_report,
)
from evaluation.registry import FORMULA_IDS, METHOD_IDS, get_formula
from evaluation.score_predictions import score_predictions_file
from evaluation.v_fixture_gold import attach_v_fixture_report_gold

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "src" / "evaluation" / "fixtures" / "b2_predictions.jsonl"
LIVE_METRICS = ROOT / "docs" / "paper-assets" / "tables" / "b2_live_n20_metrics.json"
STUB = ROOT / "docs" / "paper-assets" / "tables" / "v_vs_b2_false_endorsement.md"
V_PREDICTIONS = ROOT / "docs" / "paper-assets" / "tables" / "validator_v" / "predictions.jsonl"
V_SIDECAR = ROOT / "docs" / "paper-assets" / "tables" / "validator_v" / "run.json"
V_METRICS = ROOT / "docs" / "paper-assets" / "tables" / "validator_v" / "v_dry_run_metrics.json"
LIVE_RUN_ID = "same-evidence-b2-development-s0-n20-dac855c4e2ae"
V_RUN_ID = "validator-v-development-s0-n3-d5cecb97c55b"
FIXTURE_RUN_ID = "fixture-b2-score-001"
NOTES = "docs/paper-assets/formulas/F-false-endorsement.md"

_NUMERIC_FIELDS = (
    "false_endorsement_gold_nonsup",
    "false_endorsement_pred_sup",
    "n_false_endorsements",
    "n_gold_nonsupported",
    "n_predicted_supported",
    "n_scored",
)


def _load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _v_cells(markdown: str) -> list[str]:
    cells: list[str] = []
    for line in markdown.splitlines():
        if not line.startswith("|"):
            continue
        if line.startswith("| Metric") or line.startswith("| ---"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        cells.append(parts[-1])
    return cells


def _assert_pending(cell) -> None:
    assert cell.method_id == "V"
    assert cell.status == "pending"
    assert cell.formula_id == FORMULA_ID
    assert cell.notes_path == NOTES
    for name in _NUMERIC_FIELDS:
        assert getattr(cell, name) is None, name


def test_method_id_enum_is_b2_and_v_only():
    assert METHOD_IDS == ("B2", "V")
    assert FORMULA_ID in FORMULA_IDS
    assert get_formula(FORMULA_ID).notes_path == NOTES


def test_empty_v_refuses_fake_scores(monkeypatch):
    report = json.loads(LIVE_METRICS.read_text(encoding="utf-8"))

    def boom(*args, **kwargs):
        raise AssertionError("empty V must not be scored")

    monkeypatch.setattr("evaluation.harness.score_prediction_rows", boom)
    for empty in (None, []):
        comparison = compare_false_endorsement(b2_report=report, v_predictions=empty)
        _assert_pending(comparison.v)
        assert comparison.v_predictions_present is False
        assert comparison.b2.status == "scored"
        assert comparison.b2.run_id == LIVE_RUN_ID
        assert comparison.b2.false_endorsement_gold_nonsup == 3 / 17
        assert comparison.b2.false_endorsement_pred_sup == 1.0
        assert comparison.b2.n_false_endorsements == 3
        assert comparison.b2.n_gold_nonsupported == 17
        assert comparison.b2.n_predicted_supported == 3
        rendered = render_comparison_markdown(comparison)
        for cell in _v_cells(rendered):
            assert cell in {PENDING, EM_DASH}
            assert not any(character.isdigit() for character in cell)
        assert comparison.v.false_endorsement_gold_nonsup != comparison.b2.false_endorsement_gold_nonsup


def test_passed_v_run_id_still_has_no_numbers():
    report = json.loads(LIVE_METRICS.read_text(encoding="utf-8"))
    comparison = compare_false_endorsement(
        b2_report=report,
        v_predictions=[],
        v_run_id="v-run-not-scored",
    )
    _assert_pending(comparison.v)
    assert comparison.v.run_id == "v-run-not-scored"
    rendered = render_comparison_markdown(comparison)
    for cell in _v_cells(rendered):
        assert cell in {PENDING, EM_DASH}


def test_pending_live_stub_keeps_b2_and_formula():
    comparison = compare_live_b2()
    rendered = render_live_stub_markdown(comparison)
    assert f"[F-false-endorsement](../formulas/F-false-endorsement.md)" in rendered
    assert f"`{FORMULA_ID}`" in rendered
    assert NOTES in rendered
    assert LIVE_RUN_ID in rendered
    assert V_RUN_ID_PLACEHOLDER in rendered
    assert HELD_OUT_B2_RUN_ID_PLACEHOLDER in rendered
    assert HELD_OUT_V_RUN_ID_PLACEHOLDER in rendered
    assert PENDING in rendered
    assert EM_DASH in rendered
    decimals = set(re.findall(r"\d+\.\d+", rendered))
    assert decimals == {"0.17647058823529413", "1.0"}
    for cell in _v_cells(rendered):
        assert cell in {PENDING, EM_DASH}
        assert not any(character.isdigit() for character in cell)


def test_paper_table_keeps_live_b2_and_fills_v_from_dry_run():
    assert V_PREDICTIONS.is_file()
    assert V_SIDECAR.is_file()
    assert V_METRICS.is_file()
    text = STUB.read_text(encoding="utf-8")
    assert LIVE_RUN_ID in text
    assert V_RUN_ID in text
    assert "docs/paper-assets/tables/validator_v/predictions.jsonl" in text
    assert "docs/paper-assets/tables/validator_v/run.json" in text
    assert "src/evaluation/fixtures/v_fixture_report_gold.json" in text
    assert f"`{FORMULA_ID}`" in text
    assert NOTES in text
    assert "0.17647058823529413" in text
    assert "1.0" in text
    # V rates are scorer outputs for the dry-run (0.0 / 0.0), not B2 copies
    v_cells = _v_cells(text)
    assert f"`{V_RUN_ID}`" in v_cells
    assert "0.0" in v_cells
    assert "pending" not in v_cells
    assert EM_DASH not in v_cells
    metrics = json.loads(V_METRICS.read_text(encoding="utf-8"))
    assert metrics["run_id"] == V_RUN_ID
    assert metrics["method_id"] == "V"
    assert metrics["n_scored"] == 2
    by_metric = {
        row["metric"]: row
        for row in metrics["metrics"]
        if row["formula_id"] == FORMULA_ID
    }
    assert by_metric["false_endorsement_gold_nonsup"]["value"] == 0.0
    assert by_metric["false_endorsement_pred_sup"]["value"] == 0.0
    assert by_metric["false_endorsement_gold_nonsup"]["n_false_endorsements"] == 0
    assert by_metric["false_endorsement_gold_nonsup"]["n_gold_nonsupported"] == 1
    assert by_metric["false_endorsement_gold_nonsup"]["n_predicted_supported"] == 1
    # Regenerating the paper table is deterministic
    output = ROOT / "docs" / "paper-assets" / "tables" / "_regen_v_vs_b2.md"
    try:
        main(
            [
                "--paper-table",
                "--v-metrics-output",
                str(ROOT / "docs" / "paper-assets" / "tables" / "validator_v" / "_regen_metrics.json"),
                "--output",
                str(output),
            ]
        )
        assert output.read_text(encoding="utf-8") == text
    finally:
        if output.exists():
            output.unlink()
        regen = ROOT / "docs" / "paper-assets" / "tables" / "validator_v" / "_regen_metrics.json"
        if regen.exists():
            regen.unlink()


def test_v_against_live_report_scores_independently():
    report = json.loads(LIVE_METRICS.read_text(encoding="utf-8"))
    rows = _load_jsonl(V_PREDICTIONS)
    scored, meta = attach_v_fixture_report_gold(rows)
    comparison = compare_false_endorsement(
        b2_report=report,
        v_predictions=scored,
        v_run_id=V_RUN_ID,
        v_gold_source=meta["source"],
    )
    assert comparison.paired is False
    assert comparison.v.status == "scored"
    assert comparison.v.run_id == V_RUN_ID
    assert comparison.b2.run_id == LIVE_RUN_ID
    assert comparison.v.false_endorsement_gold_nonsup == 0.0
    assert comparison.v.false_endorsement_pred_sup == 0.0
    assert comparison.v.n_false_endorsements == 0
    assert comparison.v.n_gold_nonsupported == 1
    assert comparison.v.n_predicted_supported == 1
    assert comparison.v.n_scored == 2
    rendered = render_live_stub_markdown(comparison)
    assert V_RUN_ID in rendered
    assert "0.0" in rendered


def test_fixture_b2_only_matches_existing_scorer():
    rows = _load_jsonl(FIXTURE)
    comparison = compare_false_endorsement(
        b2_predictions=rows,
        v_predictions=None,
        b2_run_id=FIXTURE_RUN_ID,
    )
    expected = score_predictions_file(FIXTURE, run_id=FIXTURE_RUN_ID)
    expected_cell = score_from_report(expected, expected_method="B2")
    assert comparison.b2 == expected_cell
    assert comparison.b2.false_endorsement_gold_nonsup == 2 / 5
    assert comparison.b2.false_endorsement_pred_sup == 2 / 4
    assert comparison.b2.n_false_endorsements == 2
    assert comparison.b2.n_gold_nonsupported == 5
    assert comparison.b2.n_predicted_supported == 4
    assert comparison.b2.n_scored == 8
    _assert_pending(comparison.v)
    rendered = render_comparison_markdown(comparison)
    assert FORMULA_ID in rendered
    assert NOTES in rendered
    for cell in _v_cells(rendered):
        assert not any(character.isdigit() for character in cell)


def test_paired_predictions_score_both_sides_from_rows():
    b2_rows = [
        {"claim_id": "c1", "label": "SUPPORT", "label_gold": "REFUTE", "method_id": "B2"},
        {"claim_id": "c2", "label": "NEI", "label_gold": "NEI", "method_id": "B2"},
    ]
    v_rows = [
        {"claim_id": "c2", "label": "SUPPORT", "label_gold": "NEI", "method_id": "V"},
        {"claim_id": "c1", "label": "NEI", "label_gold": "REFUTE", "method_id": "V"},
    ]
    comparison = compare_false_endorsement(
        b2_predictions=b2_rows,
        v_predictions=v_rows,
        b2_run_id="b2-pair",
        v_run_id="v-pair",
    )
    assert comparison.claim_ids == ("c1", "c2")
    assert comparison.v_predictions_present is True
    assert comparison.paired is True
    assert comparison.b2.status == "scored"
    assert comparison.v.status == "scored"
    assert comparison.b2.false_endorsement_gold_nonsup == 1 / 2
    assert comparison.b2.false_endorsement_pred_sup == 1 / 1
    assert comparison.v.false_endorsement_gold_nonsup == 1 / 2
    assert comparison.v.false_endorsement_pred_sup == 1 / 1
    assert comparison.v.n_false_endorsements == 1
    assert comparison.b2.formula_id == FORMULA_ID
    assert comparison.v.formula_id == FORMULA_ID
    assert comparison.v.notes_path == NOTES
    rendered = render_comparison_markdown(comparison)
    assert "`v-pair`" in rendered
    assert "pending" not in _v_cells(rendered)


def test_mismatched_claim_ids_are_refused():
    b2_rows = [{"claim_id": "c1", "label": "NEI", "label_gold": "NEI", "method_id": "B2"}]
    v_rows = [{"claim_id": "c2", "label": "NEI", "label_gold": "NEI", "method_id": "V"}]
    with pytest.raises(CompareError, match="same claim ids"):
        compare_false_endorsement(
            b2_predictions=b2_rows,
            v_predictions=v_rows,
            b2_run_id="b2",
            v_run_id="v",
        )


def test_unknown_method_id_is_rejected():
    rows = [{"claim_id": "c1", "label": "NEI", "label_gold": "NEI", "method_id": "B0"}]
    with pytest.raises(CompareError, match="method_id enum"):
        compare_false_endorsement(b2_predictions=rows, b2_run_id="nope")


def test_empty_b2_predictions_are_rejected():
    with pytest.raises(CompareError, match="empty"):
        compare_false_endorsement(b2_predictions=[], v_predictions=None, b2_run_id="x")


def test_cli_writes_pending_v_for_the_fixture(tmp_path: Path):
    output = tmp_path / "table.md"
    main(
        [
            "--b2-predictions",
            str(FIXTURE),
            "--b2-run-id",
            FIXTURE_RUN_ID,
            "--output",
            str(output),
        ]
    )
    text = output.read_text(encoding="utf-8")
    assert FORMULA_ID in text
    assert NOTES in text
    assert "0.4" in text
    assert "0.5" in text
    for cell in _v_cells(text):
        assert cell in {PENDING, EM_DASH}
        assert not any(character.isdigit() for character in cell)


def test_fixture_gold_refuses_unknown_ok_claim():
    rows = [
        {
            "claim_id": "scifact:999999",
            "label": "NEI",
            "method_id": "V",
            "execution_status": "ok",
        }
    ]
    with pytest.raises(Exception, match="no fixture-report smoke gold"):
        attach_v_fixture_report_gold(rows)
