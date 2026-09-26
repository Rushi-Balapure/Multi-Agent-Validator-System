"""Token and latency accumulation for Run.tokens."""

from __future__ import annotations

import pytest

from validator.usage import UsageMeter, usage_from_response


def test_meter_sums_tokens_and_latency():
    meter = UsageMeter(prompt_usd_per_1m=2.0, completion_usd_per_1m=8.0)
    meter.record(prompt_tokens=1000, completion_tokens=250, latency_seconds=1.0)
    meter.record(prompt_tokens=3000, completion_tokens=750, latency_seconds=3.0)
    summary = meter.summary()
    assert summary["n_calls"] == 2
    assert summary["prompt_tokens"] == 4000
    assert summary["completion_tokens"] == 1000
    assert summary["total_tokens"] == 5000
    assert summary["latency_seconds"]["sum"] == 4.0
    assert summary["latency_seconds"]["median"] == 2.0
    assert summary["estimated_cost_usd"] == pytest.approx(pytest_approx_cost(4000, 1000, 2.0, 8.0))


def test_cost_stays_null_without_rates():
    meter = UsageMeter()
    meter.record(prompt_tokens=10, completion_tokens=5, latency_seconds=0.2)
    assert meter.summary()["estimated_cost_usd"] is None


def test_usage_from_response_reads_openai_shape():
    prompt, completion = usage_from_response(
        {"usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}
    )
    assert (prompt, completion) == (11, 7)
    assert usage_from_response({}) == (0, 0)
    assert usage_from_response({"usage": {"input_tokens": 3, "output_tokens": 4}}) == (3, 4)


def pytest_approx_cost(
    prompt_tokens: int,
    completion_tokens: int,
    prompt_rate: float,
    completion_rate: float,
) -> float:
    return (prompt_tokens * prompt_rate + completion_tokens * completion_rate) / 1_000_000.0
