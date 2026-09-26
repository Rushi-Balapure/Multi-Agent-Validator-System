"""Checkpoint, resume, bounded concurrency, and retry for batch runners.

Predictions are appended one JSONL row at a time. Resume skips claim ids
already written. Fail-closed rows stay in the file and are never silently
re-run. Transient HTTP 429 and 5xx errors are retried with exponential
backoff; other failures are left as they are.
"""

from __future__ import annotations

import json
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Callable, Iterable, Mapping, Sequence, TypeVar

RETRYABLE_HTTP_STATUS = frozenset({429, 500, 502, 503, 504})
DEFAULT_MAX_WORKERS = 8
DEFAULT_RETRIES = 4
DEFAULT_BACKOFF_SECONDS = 1.0

T = TypeVar("T")


class RetryableTransportError(RuntimeError):
    """A 429 or 5xx response that may succeed on a later attempt."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RunControlError(RuntimeError):
    """Checkpoint or worker bookkeeping failed."""


def load_completed_rows(path: Path) -> dict[str, dict]:
    """Read existing prediction rows keyed by claim_id. Last write wins."""
    if not path.is_file():
        return {}
    completed: dict[str, dict] = {}
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RunControlError(f"{path}:{line_number} is not JSON: {exc}") from exc
        if not isinstance(row, dict):
            raise RunControlError(f"{path}:{line_number} is not a JSON object")
        claim_id = row.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id:
            raise RunControlError(f"{path}:{line_number} is missing claim_id")
        completed[claim_id] = row
    return completed


def pending_items(
    items: Sequence[T],
    completed: Mapping[str, object],
    *,
    claim_id_of: Callable[[T], str],
) -> list[T]:
    """Keep items whose claim_id is not already on disk."""
    return [item for item in items if claim_id_of(item) not in completed]


def append_prediction_row(path: Path, row: dict, *, lock: Lock | None = None) -> None:
    """Append one JSONL row. Creates the parent directory if needed."""
    claim_id = row.get("claim_id")
    if not isinstance(claim_id, str) or not claim_id:
        raise RunControlError("prediction row is missing claim_id")
    text = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    guard = lock if lock is not None else Lock()

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()

    if lock is None:
        _write()
        return
    with guard:
        _write()


def rewrite_predictions(path: Path, rows: Sequence[dict]) -> None:
    """Replace the predictions file with ``rows`` in the given order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for row in rows
    )
    temporary = path.with_suffix(path.suffix + ".partial")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def call_with_retry(
    fn: Callable[[], T],
    *,
    retries: int = DEFAULT_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
    sleep: Callable[[float], None] = time.sleep,
    rng: random.Random | None = None,
) -> T:
    """Retry ``fn`` on ``RetryableTransportError`` with exponential backoff."""
    if isinstance(retries, bool) or not isinstance(retries, int) or retries < 0:
        raise RunControlError("retries must be a non-negative integer")
    last: RetryableTransportError | None = None
    jitter = rng if rng is not None else random.Random()
    for attempt in range(retries + 1):
        try:
            return fn()
        except RetryableTransportError as exc:
            last = exc
            if attempt == retries:
                raise
            delay = backoff_seconds * (2**attempt)
            delay += jitter.uniform(0.0, min(0.25, delay * 0.1))
            sleep(delay)
    assert last is not None
    raise last


def run_items(
    items: Sequence[T],
    worker: Callable[[T], dict],
    *,
    claim_id_of: Callable[[T], str],
    output: Path,
    resume: bool = True,
    max_workers: int = 1,
    retries: int = DEFAULT_RETRIES,
    backoff_seconds: float = DEFAULT_BACKOFF_SECONDS,
) -> list[dict]:
    """Run ``worker`` over ``items``, checkpointing each finished row.

    Completed claim ids are skipped when ``resume`` is true. Results are
    returned in the original ``items`` order. ``max_workers`` of 1 is
    sequential and deterministic.
    """
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
        raise RunControlError("max_workers must be a positive integer")
    completed = load_completed_rows(output) if resume else {}
    lock = Lock()

    def invoke(item: T) -> dict:
        return call_with_retry(
            lambda: worker(item),
            retries=retries,
            backoff_seconds=backoff_seconds,
        )

    pending = pending_items(items, completed, claim_id_of=claim_id_of)
    if max_workers == 1 or len(pending) <= 1:
        for item in pending:
            row = invoke(item)
            _check_row_id(row, claim_id_of(item))
            append_prediction_row(output, row, lock=lock)
            completed[row["claim_id"]] = row
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = {pool.submit(invoke, item): claim_id_of(item) for item in pending}
            for future in as_completed(futures):
                expected = futures[future]
                row = future.result()
                _check_row_id(row, expected)
                append_prediction_row(output, row, lock=lock)
                completed[row["claim_id"]] = row

    ordered: list[dict] = []
    missing: list[str] = []
    for item in items:
        claim_id = claim_id_of(item)
        row = completed.get(claim_id)
        if row is None:
            missing.append(claim_id)
            continue
        ordered.append(row)
    if missing:
        raise RunControlError(f"missing predictions for {missing[:5]}")
    rewrite_predictions(output, ordered)
    return ordered


def _check_row_id(row: dict, expected: str) -> None:
    if not isinstance(row, dict) or row.get("claim_id") != expected:
        raise RunControlError(
            f"worker returned claim_id {row.get('claim_id')!r}, expected {expected!r}"
        )


def iter_claim_ids(rows: Iterable[dict]) -> list[str]:
    return [row["claim_id"] for row in rows]
