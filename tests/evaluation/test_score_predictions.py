"""Hand-checked B2 prediction scores.

Fixture rows (gold, pred), after CONTRADICT → REFUTE:

    scifact:1 SUPPORT, SUPPORT
    scifact:2 SUPPORT, SUPPORT
    scifact:3 REFUTE,  SUPPORT
    scifact:4 REFUTE,  REFUTE
    scifact:5 NEI,     REFUTE
    scifact:6 NEI,     NEI
    scifact:7 SUPPORT, NEI
    scifact:8 REFUTE,  SUPPORT   (gold written as CONTRADICT)

scifact:9 has no gold. scifact:10 is execution_status fail (SUPPORT vs REFUTE)
and must not enter the counts. That would have been another false endorsement.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.registry import FORMULA_IDS, get_formula
from evaluation.scifact_gold import GoldJoinError, claim_label_from_native, join_scifact_gold
from evaluation.score_predictions import ScoreError, main, score_prediction_rows, score_predictions_file
from evaluation.scorers import false_endorsement

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "src" / "evaluation" / "fixtures" / "b2_predictions.jsonl"
EXPECTED = ROOT / "src" / "evaluation" / "fixtures" / "b2_metrics_expected.json"
RUN_ID = "fixture-b2-score-001"


def _prf(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    if precision + recall == 0.0:
        return precision, recall, 0.0
    return precision, recall, (2 * precision * recall) / (precision + recall)


def _index(report: dict) -> dict[tuple[str, str, str | None], dict]:
    return {(row["formula_id"], row["metric"], row["class"]): row for row in report["metrics"]}


def test_fixture_matches_hand_computed_expected():
    report = score_predictions_file(FIXTURE, run_id=RUN_ID)
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    comparable = {key: report[key] for key in expected}
    assert comparable == expected

    support = _prf(2, 2, 1)
    refute = _prf(1, 1, 2)
    nei = _prf(1, 1, 1)
    metrics = _index(report)
    assert metrics[("F-native-scifact", "precision", "SUPPORT")]["value"] == support[0]
    assert metrics[("F-native-scifact", "recall", "SUPPORT")]["value"] == support[1]
    assert metrics[("F-native-scifact", "f1", "SUPPORT")]["value"] == support[2]
    assert metrics[("F-native-scifact", "precision", "REFUTE")]["value"] == refute[0]
    assert metrics[("F-native-scifact", "recall", "REFUTE")]["value"] == refute[1]
    assert metrics[("F-native-scifact", "f1", "REFUTE")]["value"] == refute[2]
    assert metrics[("F-native-scifact", "precision", "NEI")]["value"] == nei[0]
    assert metrics[("F-native-scifact", "recall", "NEI")]["value"] == nei[1]
    assert metrics[("F-native-scifact", "f1", "NEI")]["value"] == nei[2]
    assert metrics[("F-native-scifact", "micro_f1", None)]["value"] == _prf(4, 4, 4)[2]
    assert metrics[("F-native-scifact", "macro_precision", None)]["value"] == (support[0] + refute[0] + nei[0]) / 3
    assert metrics[("F-native-scifact", "macro_recall", None)]["value"] == (support[1] + refute[1] + nei[1]) / 3
    assert metrics[("F-native-scifact", "macro_f1", None)]["value"] == (support[2] + refute[2] + nei[2]) / 3
    assert metrics[("F-false-endorsement", "false_endorsement_gold_nonsup", "SUPPORT")]["value"] == 2 / 5
    assert metrics[("F-false-endorsement", "false_endorsement_pred_sup", "SUPPORT")]["value"] == 2 / 4
    assert report["counts"]["per_class"] == {
        "SUPPORT": {"tp": 2, "fp": 2, "fn": 1},
        "REFUTE": {"tp": 1, "fp": 1, "fn": 2},
        "NEI": {"tp": 1, "fp": 1, "fn": 1},
    }
    assert report["n_rows"] == 10
    assert report["n_scored"] == 8
    assert report["n_skipped_unlabeled"] == 1
    assert report["n_skipped_not_ok"] == 1


def test_every_metric_cites_run_id_and_formula():
    report = score_predictions_file(FIXTURE, run_id=RUN_ID)
    assert report["metrics"], "expected at least one metric"
    for row in report["metrics"]:
        assert row["run_id"] == RUN_ID
        assert row["formula_id"] in FORMULA_IDS
        assert row["notes_path"] == get_formula(row["formula_id"]).notes_path
    assert report["counts"]["run_id"] == RUN_ID
    assert report["counts"]["formula_id"] in FORMULA_IDS
    cited = {row["formula_id"] for row in report["metrics"]}
    assert cited == {"F-native-scifact", "F-false-endorsement"}


def test_cli_writes_the_same_metrics(tmp_path: Path):
    output = tmp_path / "metrics.json"
    main(["--predictions", str(FIXTURE), "--run-id", RUN_ID, "--output", str(output)])
    written = json.loads(output.read_text(encoding="utf-8"))
    expected = json.loads(EXPECTED.read_text(encoding="utf-8"))
    assert {key: written[key] for key in expected} == expected
    assert written["provenance"]["run_id"] == RUN_ID


def test_run_id_comes_from_sidecar_unless_overridden(tmp_path: Path):
    sidecar = tmp_path / "run.json"
    sidecar.write_text(
        json.dumps({"inference_mode": "mock", "run": {"run_id": "sidecar-run-9"}}),
        encoding="utf-8",
    )
    from_sidecar = score_predictions_file(FIXTURE, run_sidecar=sidecar)
    assert from_sidecar["run_id"] == "sidecar-run-9"
    assert from_sidecar["metrics"][0]["run_id"] == "sidecar-run-9"
    overridden = score_predictions_file(FIXTURE, run_id="cli-wins", run_sidecar=sidecar)
    assert overridden["run_id"] == "cli-wins"


def test_missing_gold_exits_without_writing(tmp_path: Path):
    predictions = tmp_path / "predictions.jsonl"
    predictions.write_text(
        '{"claim_id": "scifact:1", "label": "NEI", "adaptation": "B2"}\n',
        encoding="utf-8",
    )
    output = tmp_path / "metrics.json"
    with pytest.raises(SystemExit) as exc:
        main(
            [
                "--predictions",
                str(predictions),
                "--run-id",
                "no-gold",
                "--output",
                str(output),
            ]
        )
    assert exc.value.code == 2
    assert not output.exists()


def test_four_way_prediction_label_is_rejected():
    rows = [{"claim_id": "scifact:1", "label": "supported", "label_gold": "SUPPORT"}]
    with pytest.raises(ScoreError, match="SUPPORT/REFUTE/NEI"):
        score_prediction_rows(rows, run_id="bad-label")


def test_absent_classes_contribute_zero_f1():
    rows = [
        {"claim_id": "a", "label": "SUPPORT", "label_gold": "SUPPORT"},
        {"claim_id": "b", "label": "SUPPORT", "label_gold": "SUPPORT"},
    ]
    report = score_prediction_rows(rows, run_id="only-support")
    metrics = _index(report)
    assert metrics[("F-native-scifact", "f1", "REFUTE")]["value"] == 0.0
    assert metrics[("F-native-scifact", "f1", "NEI")]["value"] == 0.0
    assert metrics[("F-native-scifact", "macro_f1", None)]["value"] == (1.0 + 0.0 + 0.0) / 3
    assert metrics[("F-false-endorsement", "false_endorsement_gold_nonsup", "SUPPORT")]["value"] == 0.0
    assert metrics[("F-false-endorsement", "false_endorsement_pred_sup", "SUPPORT")]["value"] == 0.0


def test_native_gold_reduction_does_not_invent_labels():
    assert claim_label_from_native([]) == "NEI"
    assert claim_label_from_native(["SUPPORT", "SUPPORT"]) == "SUPPORT"
    assert claim_label_from_native(["CONTRADICT"]) == "CONTRADICT"
    with pytest.raises(GoldJoinError, match="mixed"):
        claim_label_from_native(["SUPPORT", "CONTRADICT"])
    with pytest.raises(GoldJoinError, match="outside"):
        claim_label_from_native(["unaddressed"])


def test_join_gold_uses_locked_development_split():
    claims_path = ROOT / "data" / "raw" / "scifact" / "claims_train.jsonl"
    if not claims_path.is_file():
        pytest.skip("pinned SciFact claims are not downloaded")
    rows = [
        {"claim_id": "scifact:0", "label": "NEI", "adaptation": "B2", "inference_mode": "live"},
        {"claim_id": "scifact:2", "label": "REFUTE", "adaptation": "B2", "inference_mode": "live"},
        {"claim_id": "scifact:12", "label": "NEI", "adaptation": "B2", "inference_mode": "live"},
    ]
    sidecar = {
        "inference_mode": "live",
        "run": {
            "run_id": "join-check",
            "split": "development",
            "corpus_hash": "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62",
        },
    }
    joined, gold = join_scifact_gold(rows, split="development", sidecar=sidecar)
    by_id = {row["claim_id"]: row["label_gold"] for row in joined}
    assert by_id == {"scifact:0": "NEI", "scifact:2": "CONTRADICT", "scifact:12": "SUPPORT"}
    assert gold["n_joined"] == 3
    assert gold["claims"][2]["native_labels"] == ["SUPPORT", "SUPPORT"]
    with pytest.raises(GoldJoinError, match="not in the locked"):
        join_scifact_gold(
            [{"claim_id": "scifact:999999", "label": "NEI"}],
            split="development",
            sidecar=sidecar,
        )


def test_checked_in_live_metrics_cite_the_development_run():
    report = json.loads(
        (ROOT / "docs" / "paper-assets" / "tables" / "b2_live_n20_metrics.json").read_text(encoding="utf-8")
    )
    run_id = "same-evidence-b2-development-s0-n20-dac855c4e2ae"
    assert report["run_id"] == run_id
    assert report["inference_mode"] == "live"
    assert report["n_scored"] == 20
    assert report["counts"]["per_class"]["SUPPORT"] == {"tp": 0, "fp": 3, "fn": 3}
    assert report["counts"]["per_class"]["REFUTE"] == {"tp": 1, "fp": 3, "fn": 0}
    assert report["counts"]["per_class"]["NEI"] == {"tp": 11, "fp": 2, "fn": 5}
    metrics = _index(report)
    assert metrics[("F-native-scifact", "precision", "REFUTE")]["value"] == 0.25
    assert metrics[("F-native-scifact", "micro_f1", None)]["value"] == 0.6
    assert metrics[("F-false-endorsement", "false_endorsement_gold_nonsup", "SUPPORT")]["value"] == 3 / 17
    assert metrics[("F-false-endorsement", "false_endorsement_pred_sup", "SUPPORT")]["value"] == 1.0
    for row in report["metrics"]:
        assert row["run_id"] == run_id
        assert row["formula_id"] in {"F-native-scifact", "F-false-endorsement"}


def test_existing_false_endorsement_fixture_unchanged():
    payload = json.loads(
        (ROOT / "src" / "evaluation" / "fixtures" / "false_endorsement_input.json").read_text(encoding="utf-8")
    )
    expected = json.loads(
        (ROOT / "src" / "evaluation" / "fixtures" / "false_endorsement_expected.json").read_text(encoding="utf-8")
    )
    assert false_endorsement(payload) == expected


def test_all_failed_rows_report_skipped_not_ok_without_fe_rates():
    rows = [
        {
            "claim_id": f"scifact:{i}",
            "label": "NEI",
            "method_id": "V",
            "execution_status": "failed",
            "inference_mode": "live",
        }
        for i in range(3)
    ]
    report = score_prediction_rows(rows, run_id="gather-skip-001")
    assert report["scoring_status"] == "skipped_not_ok"
    assert report["n_rows"] == 3
    assert report["n_scored"] == 0
    assert report["n_skipped_not_ok"] == 3
    assert report["metrics"] == []
    assert report["counts"] is None


def test_checked_in_v_gather_is_entirely_fail_closed():
    path = ROOT / "docs" / "paper-assets" / "tables" / "validator_v_gather" / "predictions.jsonl"
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 20
    assert all(row.get("execution_status") == "failed" for row in rows)
    report = score_prediction_rows(
        rows, run_id="validator-v-gather-development-s0-n20-90129d9056fd"
    )
    assert report["scoring_status"] == "skipped_not_ok"
    assert report["n_skipped_not_ok"] == 20
    assert report["n_scored"] == 0
    assert report["metrics"] == []
