"""Checkpoint, resume, retry, and ordered rewrite."""

from __future__ import annotations

from pathlib import Path

import pytest

from validator.run_control import (
    RetryableTransportError,
    call_with_retry,
    load_completed_rows,
    pending_items,
    run_items,
)


def test_resume_skips_completed_and_keeps_order(tmp_path: Path):
    output = tmp_path / "predictions.jsonl"
    output.write_text(
        '{"claim_id":"scifact:2","label":"NEI"}\n',
        encoding="utf-8",
    )
    items = ["scifact:0", "scifact:2", "scifact:4"]
    seen: list[str] = []

    def worker(claim_id: str) -> dict:
        seen.append(claim_id)
        return {"claim_id": claim_id, "label": "SUPPORT"}

    rows = run_items(
        items,
        worker,
        claim_id_of=lambda item: item,
        output=output,
        resume=True,
        max_workers=1,
        retries=0,
    )
    assert seen == ["scifact:0", "scifact:4"]
    assert [row["claim_id"] for row in rows] == items
    assert rows[1]["label"] == "NEI"
    assert load_completed_rows(output)["scifact:2"]["label"] == "NEI"


def test_fail_closed_row_is_not_rerun(tmp_path: Path):
    output = tmp_path / "predictions.jsonl"
    items = ["scifact:1"]
    output.write_text(
        '{"claim_id":"scifact:1","label":"NEI","execution_status":"failed"}\n',
        encoding="utf-8",
    )
    calls = {"n": 0}

    def worker(claim_id: str) -> dict:
        calls["n"] += 1
        return {"claim_id": claim_id, "label": "SUPPORT", "execution_status": "ok"}

    rows = run_items(
        items,
        worker,
        claim_id_of=lambda item: item,
        output=output,
        resume=True,
        max_workers=1,
        retries=0,
    )
    assert calls["n"] == 0
    assert rows[0]["execution_status"] == "failed"


def test_retry_then_succeeds():
    attempts = {"n": 0}

    def flaky() -> str:
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise RetryableTransportError("429", status_code=429)
        return "ok"

    slept: list[float] = []
    assert call_with_retry(flaky, retries=3, backoff_seconds=0.01, sleep=slept.append) == "ok"
    assert attempts["n"] == 3
    assert slept


def test_retry_exhausted_raises():
    def always() -> str:
        raise RetryableTransportError("503", status_code=503)

    with pytest.raises(RetryableTransportError):
        call_with_retry(always, retries=1, backoff_seconds=0.0, sleep=lambda _: None)


def test_pending_items_filters_completed():
    items = ["a", "b", "c"]
    assert pending_items(items, {"b": {}}, claim_id_of=lambda item: item) == ["a", "c"]


def test_concurrent_run_returns_requested_order(tmp_path: Path):
    output = tmp_path / "predictions.jsonl"
    items = [f"scifact:{index}" for index in range(6)]

    def worker(claim_id: str) -> dict:
        return {"claim_id": claim_id, "label": "NEI"}

    rows = run_items(
        items,
        worker,
        claim_id_of=lambda item: item,
        output=output,
        resume=False,
        max_workers=4,
        retries=0,
    )
    assert [row["claim_id"] for row in rows] == items
    assert list(load_completed_rows(output)) == items or set(load_completed_rows(output)) == set(items)
    assert [row["claim_id"] for row in rows] == [
        line and __import__("json").loads(line)["claim_id"]
        for line in output.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
