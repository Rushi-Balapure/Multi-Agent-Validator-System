"""Tests for the fail-closed accounting and the transport-failure path.

Two behaviours are protected here.

1. ``score_prediction_rows(include_failed=True)`` scores every submitted row
   with the label the method recorded, so a method cannot look better by
   failing on the hard claims.
2. A runner whose endpoint keeps returning a retryable HTTP error records a
   failed execution status instead of aborting the batch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.score_predictions import score_prediction_rows
from validator.run_control import RetryableTransportError
from validator.same_evidence import b2 as b2_module
from validator.same_evidence.runner import _failed_b2_row


def _row(claim_id: str, label: str, status: str, gold: str) -> dict:
    return {
        "claim_id": claim_id,
        "label": label,
        "execution_status": status,
        "label_gold": gold,
        "inference_mode": "live",
    }


def test_failed_rows_are_skipped_by_default() -> None:
    rows = [
        _row("a", "SUPPORT", "ok", "SUPPORT"),
        _row("b", "NEI", "failed", "SUPPORT"),
    ]
    report = score_prediction_rows(rows, run_id="r1")
    assert report["n_scored"] == 1
    assert report["n_skipped_not_ok"] == 1
    assert report["scoring_status"] == "scored"


def test_failed_rows_can_be_scored_as_their_recorded_label() -> None:
    rows = [
        _row("a", "SUPPORT", "ok", "SUPPORT"),
        _row("b", "NEI", "failed", "SUPPORT"),
    ]
    report = score_prediction_rows(rows, run_id="r2", include_failed=True)
    assert report["n_scored"] == 2
    assert report["n_skipped_not_ok"] == 0
    assert report["scoring_status"] == "scored_all_rows"
    recall = {
        item["class"]: item["value"]
        for item in report["metrics"]
        if item["metric"] == "recall" and item["class"] == "SUPPORT"
    }
    # The failed row is scored as NEI, so it becomes a false negative.
    assert recall["SUPPORT"] == pytest.approx(0.5)


def test_fail_closed_row_is_never_a_scientific_verdict() -> None:
    class _Item:
        claim_id = "scifact:1"

    row = _failed_b2_row(_Item(), reason="endpoint returned HTTP 502", inference_mode="live")
    assert row["execution_status"] == "failed"
    assert row["label"] == "NEI"
    assert "502" in row["rationale"]


def test_retryable_transport_error_is_not_fatal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The B2 runner turns an exhausted retry budget into a failed row."""

    class _Item:
        claim_id = "scifact:2"
        normalized_claim = "c"
        gold_evidence_bundle = []
        cited_doc_ids = []
        split_role = "development"

        def nei_eligible(self) -> bool:
            return True

    from validator.same_evidence import runner as runner_module

    def _raise(*_args, **_kwargs):
        raise RetryableTransportError("endpoint returned HTTP 502", status_code=502)

    monkeypatch.setattr(runner_module, "run_b2", _raise)
    row = runner_module.run_b2_worker(
        _Item(),
        seed=0,
        prompt_texts={
            "neutral_question": "{claim}",
            "reader": "r",
            "compare": "c",
        },
        client=object(),
        mock_if_unavailable=False,
    )
    assert row["execution_status"] == "failed"
    assert "502" in row["rationale"]


def test_drop_failed_rows_keeps_the_backup(tmp_path: Path) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "paper"))
    from drop_failed_rows import main as drop_main

    path = tmp_path / "predictions.jsonl"
    path.write_text(
        "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for row in (
                _row("a", "SUPPORT", "ok", "SUPPORT"),
                _row("b", "NEI", "failed", "SUPPORT"),
            )
        ),
        encoding="utf-8",
    )
    assert drop_main(["drop_failed_rows.py", str(path)]) == 0
    remaining = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert [row["claim_id"] for row in remaining] == ["a"]
    assert path.with_suffix(path.suffix + ".failed").is_file()
