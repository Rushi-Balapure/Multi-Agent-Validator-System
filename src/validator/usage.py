"""Per-call token and latency accounting for OpenAI-compatible clients.

Rates are optional. When ``prompt_usd_per_1m`` and ``completion_usd_per_1m``
are unset, ``estimated_cost_usd`` stays null rather than inventing a price.
"""

from __future__ import annotations

import os
import statistics
from dataclasses import dataclass, field
from threading import Lock
from typing import Any


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    position = quantile * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def rates_from_env() -> tuple[float | None, float | None]:
    """Read optional USD-per-1M-token rates. Missing or blank stays None."""
    prompt = os.environ.get("OPENAI_PROMPT_USD_PER_1M")
    completion = os.environ.get("OPENAI_COMPLETION_USD_PER_1M")

    def parse(raw: str | None) -> float | None:
        if raw is None or not raw.strip():
            return None
        try:
            value = float(raw)
        except ValueError:
            return None
        if value < 0:
            return None
        return value

    return parse(prompt), parse(completion)


@dataclass
class UsageMeter:
    """Thread-safe accumulator for chat-completion usage."""

    prompt_usd_per_1m: float | None = None
    completion_usd_per_1m: float | None = None
    _lock: Lock = field(default_factory=Lock, repr=False)
    prompt_tokens: int = 0
    completion_tokens: int = 0
    n_calls: int = 0
    latencies: list[float] = field(default_factory=list)

    def record(
        self,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        latency_seconds: float | None = None,
    ) -> None:
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("token counts must be non-negative")
        with self._lock:
            self.prompt_tokens += int(prompt_tokens)
            self.completion_tokens += int(completion_tokens)
            self.n_calls += 1
            if latency_seconds is not None:
                if latency_seconds < 0:
                    raise ValueError("latency_seconds must be non-negative")
                self.latencies.append(float(latency_seconds))

    def estimated_cost_usd(self) -> float | None:
        if self.prompt_usd_per_1m is None or self.completion_usd_per_1m is None:
            return None
        return (
            self.prompt_tokens * self.prompt_usd_per_1m
            + self.completion_tokens * self.completion_usd_per_1m
        ) / 1_000_000.0

    def summary(self) -> dict[str, Any]:
        latencies = list(self.latencies)
        latency = {
            "n": len(latencies),
            "sum": sum(latencies) if latencies else 0.0,
            "mean": (sum(latencies) / len(latencies)) if latencies else None,
            "median": statistics.median(latencies) if latencies else None,
            "p95": _percentile(latencies, 0.95),
        }
        return {
            "n_calls": self.n_calls,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.prompt_tokens + self.completion_tokens,
            "latency_seconds": latency,
            "estimated_cost_usd": self.estimated_cost_usd(),
        }


def usage_from_response(parsed: dict[str, Any]) -> tuple[int, int]:
    """Read prompt/completion tokens from a chat-completions payload."""
    usage = parsed.get("usage")
    if not isinstance(usage, dict):
        return 0, 0
    prompt = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
    completion = usage.get("completion_tokens") or usage.get("output_tokens") or 0
    try:
        prompt_n = int(prompt)
        completion_n = int(completion)
    except (TypeError, ValueError):
        return 0, 0
    if prompt_n < 0 or completion_n < 0:
        return 0, 0
    return prompt_n, completion_n
