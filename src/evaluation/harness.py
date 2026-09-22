"""V versus B2 false-endorsement harness.

Accepts B2 predictions, or a B2 metrics report already scored by
``evaluation.score_predictions``, plus optional V predictions that use the
same claim ids. The primary metric is ``F-false-endorsement`` (both
denominators). ``method_id`` is ``B2`` or ``V`` only.

When V predictions are missing or empty, the V cell stays pending. Numeric
fields are ``None`` and the markdown cell is an em dash. This module does
not copy B2 rates into the V column and does not invent a V run.

The checked-in stub is ``docs/paper-assets/tables/v_vs_b2_false_endorsement.md``.
Its B2 column is the live development run already stored in
``docs/paper-assets/tables/b2_live_n20_metrics.json``.

    PYTHONPATH=src python -m evaluation.harness \\
        --output docs/paper-assets/tables/v_vs_b2_false_endorsement.md
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, Sequence

from evaluation.registry import METHOD_IDS, get_formula
from evaluation.score_predictions import (
    ScoreError,
    _execution_ok,
    _gold_label,
    _method_id,
    _read_jsonl,
    resolve_run_id,
    score_prediction_rows,
)

FORMULA_ID = "F-false-endorsement"
V_RUN_ID_PLACEHOLDER = "<V run_id>"
HELD_OUT_B2_RUN_ID_PLACEHOLDER = "<B2 held-out run_id>"
HELD_OUT_V_RUN_ID_PLACEHOLDER = "<V held-out run_id>"
PENDING = "pending"
SCORED = "scored"
EM_DASH = "\u2014"
LIVE_B2_METRICS = Path("docs/paper-assets/tables/b2_live_n20_metrics.json")

Status = Literal["scored", "pending"]

_RATE_ROWS: tuple[tuple[str, str], ...] = (
    (
        "false endorsement, gold non-supported denominator",
        "false_endorsement_gold_nonsup",
    ),
    (
        "false endorsement, predicted-supported denominator",
        "false_endorsement_pred_sup",
    ),
)
_COUNT_ROWS: tuple[tuple[str, str], ...] = (
    ("n false endorsements", "n_false_endorsements"),
    ("n gold non-supported", "n_gold_nonsupported"),
    ("n predicted supported", "n_predicted_supported"),
)


class CompareError(Exception):
    """The V-versus-B2 comparison cannot be built."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


@dataclass(frozen=True)
class FalseEndorsementScore:
    """One method's false-endorsement cell.

    Pending cells keep ``formula_id`` and a run_id placeholder. Every numeric
    field is ``None`` so a missing V run cannot be read as zero.
    """

    method_id: str
    run_id: str
    status: Status
    formula_id: str
    notes_path: str
    false_endorsement_gold_nonsup: float | None
    false_endorsement_pred_sup: float | None
    n_false_endorsements: int | None
    n_gold_nonsupported: int | None
    n_predicted_supported: int | None
    n_scored: int | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "method_id": self.method_id,
            "run_id": self.run_id,
            "status": self.status,
            "formula_id": self.formula_id,
            "notes_path": self.notes_path,
            "false_endorsement_gold_nonsup": self.false_endorsement_gold_nonsup,
            "false_endorsement_pred_sup": self.false_endorsement_pred_sup,
            "n_false_endorsements": self.n_false_endorsements,
            "n_gold_nonsupported": self.n_gold_nonsupported,
            "n_predicted_supported": self.n_predicted_supported,
            "n_scored": self.n_scored,
        }


@dataclass(frozen=True)
class VvsB2FalseEndorsement:
    """Primary comparison. ``v.status == 'pending'`` means V was not scored."""

    formula_id: str
    notes_path: str
    b2: FalseEndorsementScore
    v: FalseEndorsementScore
    claim_ids: tuple[str, ...] | None
    b2_source: str
    v_predictions_present: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "formula_id": self.formula_id,
            "notes_path": self.notes_path,
            "b2": self.b2.as_dict(),
            "v": self.v.as_dict(),
            "claim_ids": list(self.claim_ids) if self.claim_ids is not None else None,
            "b2_source": self.b2_source,
            "v_predictions_present": self.v_predictions_present,
        }


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _notes_path() -> str:
    return get_formula(FORMULA_ID).notes_path


def _require_method(method_id: str) -> str:
    if method_id not in METHOD_IDS:
        raise CompareError(f"method_id enum is {METHOD_IDS} only, got {method_id!r}")
    return method_id


def _check_declared_method(rows: Sequence[Mapping[str, Any]], expected: str) -> None:
    _require_method(expected)
    try:
        declared = _method_id(rows)
    except ScoreError as exc:
        raise CompareError(str(exc)) from exc
    if declared is None:
        return
    _require_method(declared)
    if declared != expected:
        raise CompareError(
            f"{expected} predictions declare method_id {declared!r}"
        )


def _claim_id(row: Mapping[str, Any]) -> str:
    claim_id = row.get("claim_id")
    if not isinstance(claim_id, str) or not claim_id.strip():
        raise CompareError("claim_id must be a non-empty string")
    return claim_id


def _gold_by_claim(rows: Sequence[Mapping[str, Any]], method_id: str) -> dict[str, str]:
    """Gold labels for a paired score. Every claim must be scorable."""
    found: dict[str, str] = {}
    for row in rows:
        claim_id = _claim_id(row)
        if claim_id in found:
            raise CompareError(f"duplicate claim_id {claim_id}")
        if not _execution_ok(row):
            raise CompareError(
                f"{claim_id}: {method_id} execution is not ok; "
                "paired comparison keeps the same claim ids on both sides"
            )
        try:
            gold = _gold_label(row)
        except ValueError as exc:
            raise CompareError(f"{claim_id}: {exc}") from exc
        if gold is None:
            raise CompareError(
                f"{claim_id}: {method_id} has no gold label; "
                "refusing to score a partial pair"
            )
        found[claim_id] = gold
    if not found:
        raise CompareError(f"{method_id} predictions are empty")
    return found


def _assert_same_claims(
    b2_rows: Sequence[Mapping[str, Any]],
    v_rows: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    b2_gold = _gold_by_claim(b2_rows, "B2")
    v_gold = _gold_by_claim(v_rows, "V")
    if set(b2_gold) != set(v_gold):
        missing_on_v = sorted(set(b2_gold) - set(v_gold))
        missing_on_b2 = sorted(set(v_gold) - set(b2_gold))
        raise CompareError(
            "V and B2 predictions must use the same claim ids "
            f"(missing on V: {missing_on_v or 'none'}; "
            f"missing on B2: {missing_on_b2 or 'none'})"
        )
    mismatched = sorted(
        claim_id for claim_id, gold in b2_gold.items() if v_gold[claim_id] != gold
    )
    if mismatched:
        raise CompareError(f"gold labels differ between V and B2 for {mismatched}")
    return tuple(sorted(b2_gold))


def _metric_row(report: Mapping[str, Any], metric: str) -> Mapping[str, Any]:
    matches = [
        row
        for row in report.get("metrics", [])
        if isinstance(row, Mapping)
        and row.get("formula_id") == FORMULA_ID
        and row.get("metric") == metric
    ]
    if len(matches) != 1:
        raise CompareError(
            f"B2 report must contain one {FORMULA_ID} metric {metric!r}"
        )
    return matches[0]


def _count(row: Mapping[str, Any], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise CompareError(f"B2 report metric {key} must be an integer")
    return value


def score_from_report(
    report: Mapping[str, Any],
    *,
    expected_method: str,
) -> FalseEndorsementScore:
    """Read both false-endorsement denominators from a scorer report."""
    _require_method(expected_method)
    declared = report.get("method_id")
    if declared is not None:
        if not isinstance(declared, str):
            raise CompareError("method_id on the metrics report must be a string")
        _require_method(declared)
        if declared != expected_method:
            raise CompareError(
                f"{expected_method} report declares method_id {declared!r}"
            )
    run_id = report.get("run_id")
    if not isinstance(run_id, str) or not run_id.strip():
        raise CompareError("metrics report is missing run_id")
    gold = _metric_row(report, "false_endorsement_gold_nonsup")
    pred = _metric_row(report, "false_endorsement_pred_sup")
    if gold.get("run_id") != run_id or pred.get("run_id") != run_id:
        raise CompareError("metric run_id does not match the report run_id")
    if gold.get("notes_path") != _notes_path() or pred.get("notes_path") != _notes_path():
        raise CompareError(f"metric notes_path must cite {_notes_path()}")
    gold_value = gold.get("value")
    pred_value = pred.get("value")
    if isinstance(gold_value, bool) or not isinstance(gold_value, (int, float)):
        raise CompareError("false_endorsement_gold_nonsup value must be numeric")
    if isinstance(pred_value, bool) or not isinstance(pred_value, (int, float)):
        raise CompareError("false_endorsement_pred_sup value must be numeric")
    n_false = _count(gold, "n_false_endorsements")
    n_gold = _count(gold, "n_gold_nonsupported")
    n_pred = _count(gold, "n_predicted_supported")
    if (
        _count(pred, "n_false_endorsements") != n_false
        or _count(pred, "n_gold_nonsupported") != n_gold
        or _count(pred, "n_predicted_supported") != n_pred
    ):
        raise CompareError("the two false-endorsement denominators disagree on counts")
    n_scored = report.get("n_scored")
    if isinstance(n_scored, bool) or not isinstance(n_scored, int):
        raise CompareError("metrics report n_scored must be an integer")
    return FalseEndorsementScore(
        method_id=expected_method,
        run_id=run_id,
        status=SCORED,
        formula_id=FORMULA_ID,
        notes_path=_notes_path(),
        false_endorsement_gold_nonsup=float(gold_value),
        false_endorsement_pred_sup=float(pred_value),
        n_false_endorsements=n_false,
        n_gold_nonsupported=n_gold,
        n_predicted_supported=n_pred,
        n_scored=n_scored,
    )


def _score_predictions(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_method: str,
    run_id: str | None,
) -> FalseEndorsementScore:
    if not rows:
        raise CompareError(f"{expected_method} predictions are empty; refusing to invent a score")
    _check_declared_method(rows, expected_method)
    seen: set[str] = set()
    for row in rows:
        claim_id = _claim_id(row)
        if claim_id in seen:
            raise CompareError(f"duplicate claim_id {claim_id}")
        seen.add(claim_id)
    try:
        resolved = resolve_run_id(rows, cli_run_id=run_id, sidecar=None)
        report = score_prediction_rows(rows, run_id=resolved)
    except ScoreError as exc:
        raise CompareError(str(exc)) from exc
    if report.get("method_id") is None:
        report = dict(report)
        report["method_id"] = expected_method
    return score_from_report(report, expected_method=expected_method)


def _pending_v(run_id: str | None) -> FalseEndorsementScore:
    label = V_RUN_ID_PLACEHOLDER
    if run_id is not None and run_id.strip():
        label = run_id.strip()
    return FalseEndorsementScore(
        method_id="V",
        run_id=label,
        status=PENDING,
        formula_id=FORMULA_ID,
        notes_path=_notes_path(),
        false_endorsement_gold_nonsup=None,
        false_endorsement_pred_sup=None,
        n_false_endorsements=None,
        n_gold_nonsupported=None,
        n_predicted_supported=None,
        n_scored=None,
    )


def v_predictions_are_present(v_predictions: Sequence[Mapping[str, Any]] | None) -> bool:
    """Missing ``None`` and an empty sequence are both the pending path."""
    return v_predictions is not None and len(v_predictions) > 0


def compare_false_endorsement(
    *,
    b2_predictions: Sequence[Mapping[str, Any]] | None = None,
    v_predictions: Sequence[Mapping[str, Any]] | None = None,
    b2_report: Mapping[str, Any] | None = None,
    b2_run_id: str | None = None,
    v_run_id: str | None = None,
    b2_source: str = "predictions",
) -> VvsB2FalseEndorsement:
    """Score B2 and, when V rows exist, V on the same claim ids.

    Pass ``b2_predictions`` or ``b2_report``, not both. An empty V sequence
    leaves V pending even if ``v_run_id`` is set. A non-empty V sequence
    requires B2 prediction rows so claim ids can be aligned. V is never
    scored against an aggregate B2 report.
    """
    if b2_predictions is not None and b2_report is not None:
        raise CompareError("pass B2 predictions or a B2 metrics report, not both")
    if b2_predictions is None and b2_report is None:
        raise CompareError("pass B2 predictions or a B2 metrics report")
    if b2_predictions is not None and len(b2_predictions) == 0:
        raise CompareError("B2 predictions are empty; refusing to invent a B2 score")

    present = v_predictions_are_present(v_predictions)
    claim_ids: tuple[str, ...] | None
    if present:
        if b2_predictions is None:
            raise CompareError(
                "V predictions need B2 predictions with the same claim ids; "
                "a B2 metrics report has no row alignment. Refusing to score V."
            )
        assert v_predictions is not None
        claim_ids = _assert_same_claims(b2_predictions, v_predictions)
        b2_cell = _score_predictions(b2_predictions, expected_method="B2", run_id=b2_run_id)
        v_cell = _score_predictions(v_predictions, expected_method="V", run_id=v_run_id)
        if b2_cell.n_scored != len(claim_ids) or v_cell.n_scored != len(claim_ids):
            raise CompareError(
                "paired score dropped claim ids; refusing a partial comparison"
            )
    elif b2_predictions is not None:
        b2_cell = _score_predictions(b2_predictions, expected_method="B2", run_id=b2_run_id)
        v_cell = _pending_v(v_run_id)
        claim_ids = None
    else:
        assert b2_report is not None
        b2_cell = score_from_report(b2_report, expected_method="B2")
        v_cell = _pending_v(v_run_id)
        claim_ids = None

    if v_cell.status == PENDING:
        _assert_pending_has_no_numbers(v_cell)

    return VvsB2FalseEndorsement(
        formula_id=FORMULA_ID,
        notes_path=_notes_path(),
        b2=b2_cell,
        v=v_cell,
        claim_ids=claim_ids,
        b2_source=b2_source,
        v_predictions_present=present,
    )


def _assert_pending_has_no_numbers(cell: FalseEndorsementScore) -> None:
    numeric = (
        cell.false_endorsement_gold_nonsup,
        cell.false_endorsement_pred_sup,
        cell.n_false_endorsements,
        cell.n_gold_nonsupported,
        cell.n_predicted_supported,
        cell.n_scored,
    )
    if any(value is not None for value in numeric):
        raise CompareError("pending V cell invented a numeric score")


def load_metrics_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CompareError(f"metrics report not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CompareError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise CompareError(f"{path}: expected a JSON object")
    return payload


def read_optional_predictions(path: Path | None) -> list[dict[str, Any]] | None:
    """``None`` path and an empty file are the pending V path.

    A path that does not exist is an error, so a typo is not stored as pending.
    """
    if path is None:
        return None
    if not path.is_file():
        raise CompareError(f"predictions file not found: {path}")
    if not path.read_text(encoding="utf-8").strip():
        return []
    try:
        return _read_jsonl(path)
    except ScoreError as exc:
        raise CompareError(str(exc)) from exc


def compare_live_b2(
    *,
    v_predictions: Sequence[Mapping[str, Any]] | None = None,
    metrics_path: Path | None = None,
    v_run_id: str | None = None,
) -> VvsB2FalseEndorsement:
    """B2 column from the checked-in live metrics. V stays pending when absent."""
    path = metrics_path if metrics_path is not None else repo_root() / LIVE_B2_METRICS
    report = load_metrics_report(path)
    try:
        source = str(path.relative_to(repo_root()))
    except ValueError:
        source = str(path)
    return compare_false_endorsement(
        b2_report=report,
        v_predictions=v_predictions,
        v_run_id=v_run_id,
        b2_source=source,
    )


def _format_rate(value: float | None, status: Status) -> str:
    if status != SCORED or value is None:
        return EM_DASH
    return json.dumps(value)


def _format_count(value: int | None, status: Status) -> str:
    if status != SCORED or value is None:
        return EM_DASH
    return str(value)


def _header_run(cell: FalseEndorsementScore) -> str:
    if cell.status == PENDING:
        return V_RUN_ID_PLACEHOLDER
    return cell.run_id


def _run_cell(cell: FalseEndorsementScore) -> str:
    if cell.status == PENDING:
        return PENDING
    return f"`{cell.run_id}`"


def render_comparison_markdown(comparison: VvsB2FalseEndorsement) -> str:
    """Markdown table for the primary metric. Pending V cells are em dashes."""
    if comparison.v.status == PENDING:
        v_lead = (
            "V predictions are missing or empty. V cells are pending. "
            f"An em dash (`{EM_DASH}`) is an absent score. "
            "This table does not invent V numbers."
        )
    else:
        v_lead = (
            "V and B2 are scored on the same claim ids. "
            "Rates are computed from those predictions."
        )
    b2_header = f"B2 (`{_header_run(comparison.b2)}`)"
    v_header = f"V (`{_header_run(comparison.v)}`)"
    lines = [
        "# V vs B2 false endorsement",
        "",
        (
            "Primary comparison for method_id `V` versus `B2` on "
            f"[F-false-endorsement](../formulas/F-false-endorsement.md). "
            "Both denominators are reported. `SUPPORT` is the endorsement class "
            "on the SciFact label space (`scifact_SUPPORT_REFUTE_NEI`)."
        ),
        "",
        v_lead,
        "",
        f"B2 source: `{comparison.b2_source}`.",
        "",
        f"- formula_id: `{comparison.formula_id}`",
        f"- notes: `{comparison.notes_path}`",
        f"- B2 run_id: `{comparison.b2.run_id}`",
        (
            f"- V run_id: `{comparison.v.run_id}`"
            + (" (pending)" if comparison.v.status == PENDING else "")
        ),
        (
            "- Held-out run_id placeholders, not scored in this table: "
            f"B2 `{HELD_OUT_B2_RUN_ID_PLACEHOLDER}`, "
            f"V `{HELD_OUT_V_RUN_ID_PLACEHOLDER}`"
        ),
        "",
        f"| Metric | formula_id | {b2_header} | {v_header} |",
        "| --- | --- | --- | --- |",
        (
            f"| run_id | — | {_run_cell(comparison.b2)} | {_run_cell(comparison.v)} |"
        ),
    ]
    for label, attr in _RATE_ROWS:
        b2_text = _format_rate(getattr(comparison.b2, attr), comparison.b2.status)
        v_text = _format_rate(getattr(comparison.v, attr), comparison.v.status)
        lines.append(
            f"| {label} | `{FORMULA_ID}` | {b2_text} | {v_text} |"
        )
    for label, attr in _COUNT_ROWS:
        b2_text = _format_count(getattr(comparison.b2, attr), comparison.b2.status)
        v_text = _format_count(getattr(comparison.v, attr), comparison.v.status)
        lines.append(
            f"| {label} | `{FORMULA_ID}` | {b2_text} | {v_text} |"
        )
    lines.extend(
        [
            "",
            (
                "Bootstrap by question family (claim family is the other cluster key) "
                "is configured at 2000 resamples in `src/evaluation/bootstrap.py`. "
                "That scaffold does not emit a confidence interval. "
                "Latency and token totals stay on the Run record; see "
                "[the Run field note](../run_latency_token_contract.md)."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def render_live_stub_markdown(comparison: VvsB2FalseEndorsement) -> str:
    """Paper stub. B2 numbers come from the live report; V stays pending."""
    if comparison.v.status != PENDING:
        raise CompareError(
            "the paper stub is the empty-V path; refusing to write V scores into it"
        )
    _assert_pending_has_no_numbers(comparison.v)
    page = render_comparison_markdown(comparison)
    note = (
        "The B2 column is the checked-in live development run "
        f"`{comparison.b2.run_id}` "
        f"(n scored = {comparison.b2.n_scored}), the same live column as "
        "[b2_live_vs_mock.md](b2_live_vs_mock.md). "
        "It is the development live column. Held-out run ids below are placeholders "
        "for the preregistered comparison.\n\n"
    )
    marker = "B2 source:"
    if marker not in page:
        raise CompareError("stub renderer lost the B2 source line")
    return page.replace(marker, note + marker, 1)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare B2 and optional V predictions on F-false-endorsement. "
            "Omitting V writes a pending column."
        )
    )
    parser.add_argument("--b2-predictions", type=Path, default=None)
    parser.add_argument(
        "--v-predictions",
        type=Path,
        default=None,
        help="omit, or pass an empty file, to leave V pending",
    )
    parser.add_argument(
        "--b2-metrics",
        type=Path,
        default=None,
        help="scored B2 metrics JSON; default is the checked-in live report",
    )
    parser.add_argument("--b2-run-id", default=None)
    parser.add_argument("--v-run-id", default=None)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--live-stub",
        action="store_true",
        help="write the paper stub (requires pending V)",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        v_rows = read_optional_predictions(args.v_predictions)
        if args.b2_predictions is not None:
            b2_rows = read_optional_predictions(args.b2_predictions)
            comparison = compare_false_endorsement(
                b2_predictions=b2_rows,
                v_predictions=v_rows,
                b2_run_id=args.b2_run_id,
                v_run_id=args.v_run_id,
                b2_source=str(args.b2_predictions),
            )
            text = render_comparison_markdown(comparison)
        else:
            metrics = args.b2_metrics
            comparison = compare_live_b2(
                v_predictions=v_rows,
                metrics_path=metrics,
                v_run_id=args.v_run_id,
            )
            if args.live_stub or args.v_predictions is None:
                text = render_live_stub_markdown(comparison)
            else:
                text = render_comparison_markdown(comparison)
    except CompareError as exc:
        print(f"COMPARE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(
        f"wrote {args.output} b2_run_id={comparison.b2.run_id} "
        f"v_status={comparison.v.status}"
    )


if __name__ == "__main__":
    main()
