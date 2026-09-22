"""V versus B2 false-endorsement harness.

Accepts B2 predictions, or a B2 metrics report already scored by
``evaluation.score_predictions``, plus optional V predictions. The primary
metric is ``F-false-endorsement`` (both denominators). ``method_id`` is
``B2`` or ``V`` only.

When V predictions are missing or empty, the V cell stays pending. Numeric
fields are ``None`` and the markdown cell is an em dash. This module does
not copy B2 rates into the V column and does not invent a V run.

When every V row is execution not-ok (gather fail-closed D0), the V cell is
``skipped``: FE rates stay ``N/A`` (not 0.0) and ``n_skipped_not_ok`` is
reported. Failed rows are never remapped to scorables.

When cited-D0 gather rows are mostly execution-ok, paper-table mode joins
locked SciFact development gold (``--join-gold development``) and scores
both FE denominators. Partial skips (``n_skipped_not_ok``) are reported
honestly and are never remapped to scorables.

Paired mode (B2 prediction rows + V rows) requires the same claim ids.
Paper-table mode keeps the checked-in live B2 metrics column and aligns V
gather claim ids to that set. Paired bootstrap still requires aligned
scorable claim ids.

The checked-in table is ``docs/paper-assets/tables/v_vs_b2_false_endorsement.md``.
Its B2 column is the live development run already stored in
``docs/paper-assets/tables/b2_live_n20_metrics.json``. The V column is the
Phase-3 cited-D0 gather live run under
``docs/paper-assets/tables/validator_v_gather_cited_d0/``. The fail-closed
gather set under ``validator_v_gather/`` is kept as comparison history.

    PYTHONPATH=src python -m evaluation.harness \\
        --paper-table \\
        --v-metrics-output docs/paper-assets/tables/validator_v_gather_cited_d0/v_gather_cited_d0_metrics.json \\
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
from evaluation.scifact_gold import GoldJoinError, join_scifact_gold
from evaluation.score_predictions import (
    ScoreError,
    _execution_ok,
    _gold_label,
    _method_id,
    _read_jsonl,
    resolve_run_id,
    score_prediction_rows,
)
from evaluation.v_fixture_gold import FixtureGoldError, attach_v_fixture_report_gold

FORMULA_ID = "F-false-endorsement"
V_RUN_ID_PLACEHOLDER = "<V run_id>"
HELD_OUT_B2_RUN_ID_PLACEHOLDER = "<B2 held-out run_id>"
HELD_OUT_V_RUN_ID_PLACEHOLDER = "<V held-out run_id>"
PENDING = "pending"
SCORED = "scored"
EM_DASH = "\u2014"
NA = "N/A"
SKIPPED = "skipped"
LIVE_B2_METRICS = Path("docs/paper-assets/tables/b2_live_n20_metrics.json")
DEFAULT_V_PREDICTIONS = Path(
    "docs/paper-assets/tables/validator_v_gather_cited_d0/predictions.jsonl"
)
DEFAULT_V_SIDECAR = Path(
    "docs/paper-assets/tables/validator_v_gather_cited_d0/run.json"
)
# Fail-closed gather (#23) kept as comparison history — not the paper-table default.
FAIL_CLOSED_V_PREDICTIONS = Path(
    "docs/paper-assets/tables/validator_v_gather/predictions.jsonl"
)
FAIL_CLOSED_V_SIDECAR = Path("docs/paper-assets/tables/validator_v_gather/run.json")
FAIL_CLOSED_V_RUN_ID = "validator-v-gather-development-s0-n20-90129d9056fd"
CITED_D0_V_RUN_ID = "validator-v-gather-development-s0-n20-3c856362819b"
DEFAULT_JOIN_GOLD = "development"
# Offline fixture-report dry-run (synthetic e2e claim ids); kept for regen checks.
FIXTURE_V_PREDICTIONS = Path("docs/paper-assets/tables/validator_v/predictions.jsonl")
FIXTURE_V_SIDECAR = Path("docs/paper-assets/tables/validator_v/run.json")

Status = Literal["scored", "pending", "skipped"]

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

    Skipped cells (all rows ``execution_status`` not ok / fail-closed) keep
    ``n_scored=0`` and skip counts. FE rates stay ``None`` — never invent 0.0.
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
    n_rows: int | None = None
    n_skipped_not_ok: int | None = None
    n_skipped_unlabeled: int | None = None
    scoring_status: str | None = None

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
            "n_rows": self.n_rows,
            "n_skipped_not_ok": self.n_skipped_not_ok,
            "n_skipped_unlabeled": self.n_skipped_unlabeled,
            "scoring_status": self.scoring_status,
        }


@dataclass(frozen=True)
class VvsB2FalseEndorsement:
    """Primary comparison. ``v.status == 'pending'`` means V was not scored.

    ``v.status == 'skipped'`` means V rows were present but every row was
    skipped as not-ok (fail-closed); FE rates are absent, not zero.
    """

    formula_id: str
    notes_path: str
    b2: FalseEndorsementScore
    v: FalseEndorsementScore
    claim_ids: tuple[str, ...] | None
    b2_source: str
    v_predictions_present: bool
    paired: bool = False
    paired_claim_ids: bool = False
    v_predictions_path: str | None = None
    v_run_sidecar_path: str | None = None
    v_gold_source: str | None = None
    fail_closed_note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "formula_id": self.formula_id,
            "notes_path": self.notes_path,
            "b2": self.b2.as_dict(),
            "v": self.v.as_dict(),
            "claim_ids": list(self.claim_ids) if self.claim_ids is not None else None,
            "b2_source": self.b2_source,
            "v_predictions_present": self.v_predictions_present,
            "paired": self.paired,
            "paired_claim_ids": self.paired_claim_ids,
            "v_predictions_path": self.v_predictions_path,
            "v_run_sidecar_path": self.v_run_sidecar_path,
            "v_gold_source": self.v_gold_source,
            "fail_closed_note": self.fail_closed_note,
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


def _claim_ids_only(rows: Sequence[Mapping[str, Any]], method_id: str) -> tuple[str, ...]:
    """Claim ids without requiring execution_ok or gold (fail-closed rows allowed)."""
    found: list[str] = []
    seen: set[str] = set()
    for row in rows:
        claim_id = _claim_id(row)
        if claim_id in seen:
            raise CompareError(f"duplicate claim_id {claim_id}")
        seen.add(claim_id)
        found.append(claim_id)
    if not found:
        raise CompareError(f"{method_id} predictions are empty")
    return tuple(sorted(found))


def claim_ids_from_b2_metrics(report: Mapping[str, Any]) -> tuple[str, ...]:
    """Claim ids from a scored B2 metrics report's gold_join (paired alignment)."""
    gold_join = report.get("gold_join")
    if not isinstance(gold_join, Mapping):
        raise CompareError("B2 metrics report is missing gold_join for paired claim ids")
    claims = gold_join.get("claims")
    if not isinstance(claims, list) or not claims:
        raise CompareError("B2 metrics gold_join.claims is empty")
    ids: list[str] = []
    seen: set[str] = set()
    for entry in claims:
        if not isinstance(entry, Mapping):
            raise CompareError("B2 metrics gold_join.claims entries must be objects")
        claim_id = entry.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise CompareError("B2 metrics gold_join claim_id must be a non-empty string")
        if claim_id in seen:
            raise CompareError(f"duplicate claim_id in B2 gold_join: {claim_id}")
        seen.add(claim_id)
        ids.append(claim_id)
    return tuple(sorted(ids))


def _assert_claim_id_sets_match(
    b2_ids: Sequence[str],
    v_ids: Sequence[str],
) -> tuple[str, ...]:
    if set(b2_ids) != set(v_ids):
        missing_on_v = sorted(set(b2_ids) - set(v_ids))
        missing_on_b2 = sorted(set(v_ids) - set(b2_ids))
        raise CompareError(
            "V and B2 predictions must use the same claim ids "
            f"(missing on V: {missing_on_v or 'none'}; "
            f"missing on B2: {missing_on_b2 or 'none'})"
        )
    return tuple(sorted(b2_ids))


def _fail_closed_note(cell: FalseEndorsementScore) -> str | None:
    if cell.status != SKIPPED:
        return None
    n_skip = cell.n_skipped_not_ok if cell.n_skipped_not_ok is not None else 0
    n_rows = cell.n_rows if cell.n_rows is not None else 0
    return (
        f"V gather fail-closed D0: every prediction row has execution_status "
        f"not ok ({n_skip}/{n_rows} skipped as n_skipped_not_ok). "
        "Gather does not load gold D0 citations, so the auditor fail-closes and "
        "the reconciled label maps to underdetermined/NEI. "
        "F-false-endorsement rates are N/A — not 0.0 — because no row entered "
        "the FE denominators. Do not remap failed rows to scorables."
    )


def _cited_d0_history_note(cell: FalseEndorsementScore) -> str | None:
    """Facts-only note when the paper table scores cited-D0 rather than fail-closed."""
    if cell.status != SCORED or cell.run_id != CITED_D0_V_RUN_ID:
        return None
    n_skip = cell.n_skipped_not_ok if cell.n_skipped_not_ok is not None else 0
    n_scored = cell.n_scored if cell.n_scored is not None else 0
    return (
        "Comparison history (facts only): fail-closed gather (#23) under "
        "`docs/paper-assets/tables/validator_v_gather/` "
        f"(`{FAIL_CLOSED_V_RUN_ID}`) had `n_skipped_not_ok=20` / `n_scored=0` "
        "(FE N/A). Cited-D0 gather (#26) under "
        "`docs/paper-assets/tables/validator_v_gather_cited_d0/` "
        f"(`{CITED_D0_V_RUN_ID}`) has "
        f"`n_skipped_not_ok={n_skip}` / `n_scored={n_scored}`. "
        "The fail-closed set is kept for comparison and is not overwritten."
    )


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
    """Read both false-endorsement denominators from a scorer report.

    Reports with ``scoring_status == 'skipped_not_ok'`` (and empty metrics)
    become a skipped cell: FE rates stay ``None``.
    """
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

    n_rows = report.get("n_rows")
    n_skipped_not_ok = report.get("n_skipped_not_ok")
    n_skipped_unlabeled = report.get("n_skipped_unlabeled")
    n_scored = report.get("n_scored")
    scoring_status = report.get("scoring_status")

    if scoring_status == "skipped_not_ok" or (
        isinstance(n_scored, int)
        and n_scored == 0
        and isinstance(n_skipped_not_ok, int)
        and isinstance(n_rows, int)
        and n_skipped_not_ok == n_rows
        and n_rows > 0
        and not report.get("metrics")
    ):
        if not isinstance(n_scored, int) or n_scored != 0:
            raise CompareError("skipped_not_ok report must have n_scored == 0")
        if not isinstance(n_skipped_not_ok, int) or not isinstance(n_rows, int):
            raise CompareError("skipped_not_ok report missing skip counts")
        return FalseEndorsementScore(
            method_id=expected_method,
            run_id=run_id,
            status=SKIPPED,
            formula_id=FORMULA_ID,
            notes_path=_notes_path(),
            false_endorsement_gold_nonsup=None,
            false_endorsement_pred_sup=None,
            n_false_endorsements=None,
            n_gold_nonsupported=None,
            n_predicted_supported=None,
            n_scored=0,
            n_rows=n_rows,
            n_skipped_not_ok=n_skipped_not_ok,
            n_skipped_unlabeled=n_skipped_unlabeled
            if isinstance(n_skipped_unlabeled, int)
            else 0,
            scoring_status="skipped_not_ok",
        )

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
        n_rows=n_rows if isinstance(n_rows, int) else None,
        n_skipped_not_ok=n_skipped_not_ok
        if isinstance(n_skipped_not_ok, int)
        else None,
        n_skipped_unlabeled=n_skipped_unlabeled
        if isinstance(n_skipped_unlabeled, int)
        else None,
        scoring_status=scoring_status if isinstance(scoring_status, str) else "scored",
    )


def _score_predictions(
    rows: Sequence[Mapping[str, Any]],
    *,
    expected_method: str,
    run_id: str | None,
    join_gold: str | None = None,
    sidecar: Mapping[str, Any] | None = None,
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
    scored_rows: Sequence[Mapping[str, Any]] = rows
    try:
        if join_gold:
            scored_rows, _gold_join = join_scifact_gold(
                rows, split=join_gold, sidecar=sidecar
            )
        resolved = resolve_run_id(scored_rows, cli_run_id=run_id, sidecar=sidecar)
        report = score_prediction_rows(scored_rows, run_id=resolved)
    except (ScoreError, GoldJoinError) as exc:
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
    v_predictions_path: str | None = None,
    v_run_sidecar_path: str | None = None,
    v_gold_source: str | None = None,
    align_claim_ids_with_b2_metrics: bool = False,
    join_gold: str | None = None,
    v_sidecar: Mapping[str, Any] | None = None,
) -> VvsB2FalseEndorsement:
    """Score B2 and, when V rows exist, V.

    Pass ``b2_predictions`` or ``b2_report``, not both. An empty V sequence
    leaves V pending even if ``v_run_id`` is set.

    With B2 prediction rows, a non-empty V sequence must use the same claim
    ids. If every V row is execution not-ok (fail-closed), FE rates stay
    N/A and ``paired_claim_ids`` records the shared claim set.

    With a B2 metrics report, set ``align_claim_ids_with_b2_metrics`` to
    require V claim ids match ``gold_join`` (Phase-3 paired table).

    ``join_gold`` attaches locked SciFact labels before scoring V (and B2
    prediction rows when provided). Failures stay skipped; they are never
    remapped to scorables.
    """
    if b2_predictions is not None and b2_report is not None:
        raise CompareError("pass B2 predictions or a B2 metrics report, not both")
    if b2_predictions is None and b2_report is None:
        raise CompareError("pass B2 predictions or a B2 metrics report")
    if b2_predictions is not None and len(b2_predictions) == 0:
        raise CompareError("B2 predictions are empty; refusing to invent a B2 score")

    present = v_predictions_are_present(v_predictions)
    claim_ids: tuple[str, ...] | None = None
    paired = False
    paired_claim_ids = False
    if present:
        assert v_predictions is not None
        if b2_predictions is not None:
            v_cell = _score_predictions(
                v_predictions,
                expected_method="V",
                run_id=v_run_id,
                join_gold=join_gold,
                sidecar=v_sidecar,
            )
            b2_cell = _score_predictions(
                b2_predictions,
                expected_method="B2",
                run_id=b2_run_id,
                join_gold=join_gold,
                sidecar=None,
            )
            if v_cell.status == SKIPPED:
                claim_ids = _assert_claim_id_sets_match(
                    _claim_ids_only(b2_predictions, "B2"),
                    _claim_ids_only(v_predictions, "V"),
                )
                if b2_cell.status != SCORED or b2_cell.n_scored != len(claim_ids):
                    raise CompareError(
                        "paired claim-id alignment requires a fully scored B2 side"
                    )
                paired_claim_ids = True
                paired = False
            else:
                claim_ids = _assert_same_claims(b2_predictions, v_predictions)
                if b2_cell.n_scored != len(claim_ids) or v_cell.n_scored != len(claim_ids):
                    raise CompareError(
                        "paired score dropped claim ids; refusing a partial comparison"
                    )
                paired = True
                paired_claim_ids = True
        else:
            assert b2_report is not None
            b2_cell = score_from_report(b2_report, expected_method="B2")
            v_cell = _score_predictions(
                v_predictions,
                expected_method="V",
                run_id=v_run_id,
                join_gold=join_gold,
                sidecar=v_sidecar,
            )
            if align_claim_ids_with_b2_metrics:
                claim_ids = _assert_claim_id_sets_match(
                    claim_ids_from_b2_metrics(b2_report),
                    _claim_ids_only(v_predictions, "V"),
                )
                paired_claim_ids = True
                # Full paired (equal n_scored) requires every claim scorable on both sides.
                paired = (
                    v_cell.status == SCORED
                    and b2_cell.status == SCORED
                    and isinstance(v_cell.n_scored, int)
                    and isinstance(b2_cell.n_scored, int)
                    and v_cell.n_scored == len(claim_ids)
                    and b2_cell.n_scored == len(claim_ids)
                )
            else:
                claim_ids = None
                paired = False
    elif b2_predictions is not None:
        b2_cell = _score_predictions(
            b2_predictions,
            expected_method="B2",
            run_id=b2_run_id,
            join_gold=join_gold,
            sidecar=None,
        )
        v_cell = _pending_v(v_run_id)
    else:
        assert b2_report is not None
        b2_cell = score_from_report(b2_report, expected_method="B2")
        v_cell = _pending_v(v_run_id)

    if v_cell.status == PENDING:
        _assert_pending_has_no_numbers(v_cell)
    if v_cell.status == SKIPPED:
        _assert_skipped_has_no_fe_rates(v_cell)

    history = _cited_d0_history_note(v_cell)
    fail_closed = _fail_closed_note(v_cell)
    return VvsB2FalseEndorsement(
        formula_id=FORMULA_ID,
        notes_path=_notes_path(),
        b2=b2_cell,
        v=v_cell,
        claim_ids=claim_ids,
        b2_source=b2_source,
        v_predictions_present=present,
        paired=paired,
        paired_claim_ids=paired_claim_ids,
        v_predictions_path=v_predictions_path,
        v_run_sidecar_path=v_run_sidecar_path,
        v_gold_source=v_gold_source,
        fail_closed_note=fail_closed or history,
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


def _assert_skipped_has_no_fe_rates(cell: FalseEndorsementScore) -> None:
    if cell.false_endorsement_gold_nonsup is not None:
        raise CompareError("skipped V cell invented false_endorsement_gold_nonsup")
    if cell.false_endorsement_pred_sup is not None:
        raise CompareError("skipped V cell invented false_endorsement_pred_sup")
    if cell.n_false_endorsements is not None:
        raise CompareError("skipped V cell invented n_false_endorsements")
    if cell.n_scored != 0:
        raise CompareError("skipped V cell must have n_scored == 0")
    if cell.n_skipped_not_ok is None or cell.n_skipped_not_ok <= 0:
        raise CompareError("skipped V cell missing n_skipped_not_ok")


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


def read_run_sidecar(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.is_file():
        raise CompareError(f"run sidecar not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CompareError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise CompareError(f"{path}: expected a JSON object")
    return payload


def resolve_v_run_id(
    *,
    cli_run_id: str | None,
    sidecar: Mapping[str, Any] | None,
) -> str | None:
    if cli_run_id is not None and cli_run_id.strip():
        return cli_run_id.strip()
    if sidecar is None:
        return None
    run = sidecar.get("run")
    if isinstance(run, Mapping):
        run_id = run.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            return run_id.strip()
    return None


def compare_live_b2(
    *,
    v_predictions: Sequence[Mapping[str, Any]] | None = None,
    metrics_path: Path | None = None,
    v_run_id: str | None = None,
    v_predictions_path: str | None = None,
    v_run_sidecar_path: str | None = None,
    v_gold_source: str | None = None,
    align_claim_ids_with_b2_metrics: bool = True,
    join_gold: str | None = None,
    v_sidecar: Mapping[str, Any] | None = None,
) -> VvsB2FalseEndorsement:
    """B2 column from the checked-in live metrics.

    When V predictions are present, claim ids are aligned to the B2
    ``gold_join`` set (Phase-3 paired table) unless alignment is disabled.
    """
    path = metrics_path if metrics_path is not None else repo_root() / LIVE_B2_METRICS
    report = load_metrics_report(path)
    try:
        source = str(path.relative_to(repo_root()))
    except ValueError:
        source = str(path)
    align = align_claim_ids_with_b2_metrics and v_predictions_are_present(v_predictions)
    return compare_false_endorsement(
        b2_report=report,
        v_predictions=v_predictions,
        v_run_id=v_run_id,
        b2_source=source,
        v_predictions_path=v_predictions_path,
        v_run_sidecar_path=v_run_sidecar_path,
        v_gold_source=v_gold_source,
        align_claim_ids_with_b2_metrics=align,
        join_gold=join_gold,
        v_sidecar=v_sidecar,
    )


def _format_rate(value: float | None, status: Status) -> str:
    if status == SKIPPED:
        return NA
    if status != SCORED or value is None:
        return EM_DASH
    return json.dumps(value)


def _format_count(value: int | None, status: Status) -> str:
    if status == SKIPPED:
        return NA
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
    if cell.status == SKIPPED:
        return f"`{cell.run_id}` (skipped)"
    return f"`{cell.run_id}`"


_NEXT_CONTRACT_NOTE = (
    "**Next contract (not implemented in this MR):** a separate D1-mapped "
    "label column scored without remapping fail-closed D0 rows into SUPPORT "
    "rates. Do not silently remap `execution_status=failed` to scorables. "
    "Cited-D0 gather (non-gold proposer citations as D0) is the scored V "
    "column in this table; the fail-closed set under `validator_v_gather/` "
    "remains comparison history."
)


def _v_count_bullets(comparison: VvsB2FalseEndorsement) -> list[str]:
    """Honest row/skip counts when V was scored or fully skipped."""
    if comparison.v.status not in {SCORED, SKIPPED}:
        return []
    lines = [
        f"- V n_rows: `{comparison.v.n_rows}`",
        f"- V n_scored: `{comparison.v.n_scored}`",
        f"- V n_skipped_not_ok: `{comparison.v.n_skipped_not_ok}`",
        f"- V n_skipped_unlabeled: `{comparison.v.n_skipped_unlabeled}`",
        (
            f"- V B2 sidecar (live): `docs/paper-assets/tables/b2_live_n20_metrics.json` "
            f"(run `{comparison.b2.run_id}`)"
        ),
    ]
    return lines


def _append_skip_table_rows(lines: list[str], comparison: VvsB2FalseEndorsement) -> None:
    if comparison.v.status not in {SCORED, SKIPPED}:
        return
    if comparison.v.status == SCORED and not (
        isinstance(comparison.v.n_skipped_not_ok, int) and comparison.v.n_skipped_not_ok > 0
    ):
        # Still report n_scored for scored cited-D0 so denominators are auditable.
        pass
    lines.append(
        f"| n_skipped_not_ok | — | "
        f"{comparison.b2.n_skipped_not_ok if comparison.b2.n_skipped_not_ok is not None else 0} | "
        f"{comparison.v.n_skipped_not_ok} |"
    )
    lines.append(
        f"| n_scored | — | {comparison.b2.n_scored} | {comparison.v.n_scored} |"
    )


def render_comparison_markdown(comparison: VvsB2FalseEndorsement) -> str:
    """Markdown table for the primary metric. Pending V cells are em dashes."""
    if comparison.v.status == PENDING:
        v_lead = (
            "V predictions are missing or empty. V cells are pending. "
            f"An em dash (`{EM_DASH}`) is an absent score. "
            "This table does not invent V numbers."
        )
    elif comparison.v.status == SKIPPED:
        v_lead = (
            "V predictions are present on the same claim ids as B2, but every "
            "V row was skipped as not-ok (fail-closed D0). "
            f"FE cells are `{NA}` (not 0.0). "
            "Rates are not invented from reconciled NEI labels."
        )
    elif comparison.paired:
        v_lead = (
            "V and B2 are scored on the same claim ids. "
            "Rates are computed from those predictions."
        )
    elif comparison.paired_claim_ids:
        v_lead = (
            "V and B2 share the same claim ids (paired claim set). "
            "FE rates come from `evaluation.score_predictions` on each side."
        )
    else:
        v_lead = (
            "V is scored from its own predictions (independent of the B2 claim set). "
            "Rates come from `evaluation.score_predictions` on that run_id. "
            "This is not yet the paired same-claim-id comparison."
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
            + (
                " (pending)"
                if comparison.v.status == PENDING
                else (" (skipped_not_ok)" if comparison.v.status == SKIPPED else "")
            )
        ),
        (
            "- Held-out run_id placeholders, not scored in this table: "
            f"B2 `{HELD_OUT_B2_RUN_ID_PLACEHOLDER}`, "
            f"V `{HELD_OUT_V_RUN_ID_PLACEHOLDER}`"
        ),
    ]
    if comparison.v_predictions_path:
        lines.append(f"- V predictions: `{comparison.v_predictions_path}`")
    if comparison.v_run_sidecar_path:
        lines.append(f"- V run sidecar: `{comparison.v_run_sidecar_path}`")
    if comparison.v_gold_source:
        lines.append(f"- V gold source: `{comparison.v_gold_source}`")
    if comparison.paired_claim_ids and comparison.claim_ids is not None:
        lines.append(
            f"- paired claim ids (n={len(comparison.claim_ids)}): "
            + ", ".join(f"`{c}`" for c in comparison.claim_ids)
        )
    lines.extend(_v_count_bullets(comparison))
    if comparison.fail_closed_note:
        lines.extend(["", comparison.fail_closed_note])
    lines.extend(
        [
            "",
            f"| Metric | formula_id | {b2_header} | {v_header} |",
            "| --- | --- | --- | --- |",
            (
                f"| run_id | — | {_run_cell(comparison.b2)} | {_run_cell(comparison.v)} |"
            ),
        ]
    )
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
    _append_skip_table_rows(lines, comparison)
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
    if comparison.v.status in {SKIPPED, SCORED}:
        lines.extend([_NEXT_CONTRACT_NOTE, ""])
    return "\n".join(lines)


def render_live_stub_markdown(comparison: VvsB2FalseEndorsement) -> str:
    """Paper table. B2 numbers come from the live report; V may be pending, scored, or skipped."""
    page = render_comparison_markdown(comparison)
    if comparison.v.status == PENDING:
        _assert_pending_has_no_numbers(comparison.v)
        note = (
            "The B2 column is the checked-in live development run "
            f"`{comparison.b2.run_id}` "
            f"(n scored = {comparison.b2.n_scored}), the same live column as "
            "[b2_live_vs_mock.md](b2_live_vs_mock.md). "
            "It is the development live column. Held-out run ids below are placeholders "
            "for the preregistered comparison.\n\n"
        )
    elif comparison.v.status == SKIPPED:
        _assert_skipped_has_no_fe_rates(comparison.v)
        note = (
            "The B2 column is the checked-in live development run "
            f"`{comparison.b2.run_id}` "
            f"(n scored = {comparison.b2.n_scored}), the same live column as "
            "[b2_live_vs_mock.md](b2_live_vs_mock.md). "
            f"The V column is gather run `{comparison.v.run_id}` "
            f"(n scored = {comparison.v.n_scored}, "
            f"n_skipped_not_ok = {comparison.v.n_skipped_not_ok}). "
            "Claim ids match the B2 live set (paired claim alignment). "
            "Held-out run ids below are placeholders "
            "for the preregistered comparison.\n\n"
        )
    else:
        skip_bit = (
            f", n_skipped_not_ok = {comparison.v.n_skipped_not_ok}"
            if comparison.v.n_skipped_not_ok is not None
            else ""
        )
        if comparison.v.run_id == CITED_D0_V_RUN_ID:
            v_desc = (
                f"The V column is cited-D0 gather run `{comparison.v.run_id}` "
                f"(n scored = {comparison.v.n_scored}{skip_bit}). "
                "Claim ids match the B2 live set (paired claim alignment). "
            )
        else:
            v_desc = (
                f"The V column is run `{comparison.v.run_id}` "
                f"(n scored = {comparison.v.n_scored}{skip_bit}). "
            )
        note = (
            "The B2 column is the checked-in live development run "
            f"`{comparison.b2.run_id}` "
            f"(n scored = {comparison.b2.n_scored}), the same live column as "
            "[b2_live_vs_mock.md](b2_live_vs_mock.md). "
            + v_desc
            + "Held-out run ids below are placeholders "
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
        "--v-run-sidecar",
        type=Path,
        default=None,
        help="optional V run.json; supplies run_id when --v-run-id is omitted",
    )
    parser.add_argument(
        "--b2-metrics",
        type=Path,
        default=None,
        help="scored B2 metrics JSON; default is the checked-in live report",
    )
    parser.add_argument("--b2-run-id", default=None)
    parser.add_argument("--v-run-id", default=None)
    parser.add_argument(
        "--attach-v-fixture-gold",
        action="store_true",
        help=(
            "attach evaluation smoke gold for Stack V fixture-report claim ids "
            "(synthetic e2e ids not in the locked development split)"
        ),
    )
    parser.add_argument(
        "--v-metrics-output",
        type=Path,
        default=None,
        help="optional path to write the scored V metrics JSON",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--live-stub",
        action="store_true",
        help="write the paper table with the live-B2 note (pending or scored V)",
    )
    parser.add_argument(
        "--paper-table",
        action="store_true",
        help=(
            "fill the paper table from the checked-in live B2 metrics and the "
            "default validator_v_gather_cited_d0 artifacts under docs/paper-assets/tables/"
        ),
    )
    parser.add_argument(
        "--paper-table-fixture-v",
        action="store_true",
        help=(
            "fill the paper table using the offline fixture-report dry-run under "
            "docs/paper-assets/tables/validator_v/ (synthetic e2e claim ids)"
        ),
    )
    parser.add_argument(
        "--join-gold",
        default=None,
        help=(
            "locked SciFact split for V (and B2 prediction-row) gold join; "
            "paper-table defaults to development"
        ),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        v_pred_path = args.v_predictions
        v_sidecar_path = args.v_run_sidecar
        attach_gold = args.attach_v_fixture_gold
        join_gold = args.join_gold
        if args.paper_table_fixture_v:
            root = repo_root()
            if v_pred_path is None:
                v_pred_path = root / FIXTURE_V_PREDICTIONS
            if v_sidecar_path is None:
                v_sidecar_path = root / FIXTURE_V_SIDECAR
            attach_gold = True
            join_gold = None
            args.live_stub = True
            args.paper_table = True
        elif args.paper_table:
            root = repo_root()
            if v_pred_path is None:
                v_pred_path = root / DEFAULT_V_PREDICTIONS
            if v_sidecar_path is None:
                v_sidecar_path = root / DEFAULT_V_SIDECAR
            # Cited-D0 gather live rows use development claim ids; join locked gold.
            attach_gold = False
            if join_gold is None:
                join_gold = DEFAULT_JOIN_GOLD
            args.live_stub = True

        v_rows = read_optional_predictions(v_pred_path)
        sidecar = read_run_sidecar(v_sidecar_path)
        v_run_id = resolve_v_run_id(cli_run_id=args.v_run_id, sidecar=sidecar)
        v_gold_source = None
        if v_rows is not None and attach_gold and v_predictions_are_present(v_rows):
            try:
                v_rows, gold_meta = attach_v_fixture_report_gold(v_rows)
            except FixtureGoldError as exc:
                raise CompareError(str(exc)) from exc
            v_gold_source = gold_meta["source"]
        elif join_gold and v_rows is not None and v_predictions_are_present(v_rows):
            v_gold_source = f"data.scifact_loader.load_split:{join_gold}"

        v_pred_cite = None
        v_side_cite = None
        if v_pred_path is not None:
            try:
                v_pred_cite = str(v_pred_path.relative_to(repo_root()))
            except ValueError:
                v_pred_cite = str(v_pred_path)
        if v_sidecar_path is not None:
            try:
                v_side_cite = str(v_sidecar_path.relative_to(repo_root()))
            except ValueError:
                v_side_cite = str(v_sidecar_path)

        if args.b2_predictions is not None:
            b2_rows = read_optional_predictions(args.b2_predictions)
            comparison = compare_false_endorsement(
                b2_predictions=b2_rows,
                v_predictions=v_rows,
                b2_run_id=args.b2_run_id,
                v_run_id=v_run_id,
                b2_source=str(args.b2_predictions),
                v_predictions_path=v_pred_cite,
                v_run_sidecar_path=v_side_cite,
                v_gold_source=v_gold_source,
                join_gold=join_gold,
                v_sidecar=sidecar,
            )
            text = render_comparison_markdown(comparison)
        else:
            metrics = args.b2_metrics
            # Paper / gather path aligns claim ids to the live B2 gold_join.
            align = bool(args.paper_table) or v_pred_path is not None
            comparison = compare_live_b2(
                v_predictions=v_rows,
                metrics_path=metrics,
                v_run_id=v_run_id,
                v_predictions_path=v_pred_cite,
                v_run_sidecar_path=v_side_cite,
                v_gold_source=v_gold_source,
                align_claim_ids_with_b2_metrics=align
                and not args.paper_table_fixture_v
                and not attach_gold,
                join_gold=join_gold,
                v_sidecar=sidecar,
            )
            if args.live_stub or args.paper_table or v_pred_path is None:
                text = render_live_stub_markdown(comparison)
            else:
                text = render_comparison_markdown(comparison)

        if args.v_metrics_output is not None and comparison.v.status in {SCORED, SKIPPED}:
            if v_rows is None or not v_predictions_are_present(v_rows):
                raise CompareError("cannot write V metrics without V predictions")
            try:
                scored_rows: Sequence[Mapping[str, Any]] = v_rows
                gold_join = None
                if join_gold:
                    scored_rows, gold_join = join_scifact_gold(
                        v_rows, split=join_gold, sidecar=sidecar
                    )
                resolved = resolve_run_id(
                    scored_rows, cli_run_id=v_run_id, sidecar=sidecar
                )
                report = score_prediction_rows(scored_rows, run_id=resolved)
            except (ScoreError, GoldJoinError) as exc:
                raise CompareError(str(exc)) from exc
            if report.get("method_id") is None:
                report = dict(report)
                report["method_id"] = "V"
            report["provenance"] = {
                "predictions": v_pred_cite,
                "run_sidecar": v_side_cite,
                "gold_source": v_gold_source,
                "join_gold": join_gold,
                "run_id": resolved,
            }
            if gold_join is not None:
                report["gold_join"] = gold_join
            args.v_metrics_output.parent.mkdir(parents=True, exist_ok=True)
            args.v_metrics_output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    except CompareError as exc:
        print(f"COMPARE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding="utf-8")
    print(
        f"wrote {args.output} b2_run_id={comparison.b2.run_id} "
        f"v_status={comparison.v.status}"
        + (
            f" v_run_id={comparison.v.run_id}"
            if comparison.v.status in {SCORED, SKIPPED}
            else ""
        )
    )


if __name__ == "__main__":
    main()
