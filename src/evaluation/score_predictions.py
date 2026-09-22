"""Score a B2 same-evidence predictions.jsonl file.

Reads claim-level rows whose predicted label is SUPPORT, REFUTE, or NEI
and writes precision, recall, and F1 (per class, micro, and macro) plus
both F-false-endorsement denominators. Every metric cites ``run_id`` and
a formula id from the metric contract.

Gold is optional on the artifact. Rows without gold are counted and
skipped. If no row has gold, the command exits 2 and writes nothing:
this scorer does not join the corpus.

``run_id`` comes from ``--run-id`` or from the run sidecar
(``run.run_id``). A live B2 artifact is not in this repo. After Baseline
writes one (including the ``inference_mode=live`` rename; today's live
call records ``inference_mode=endpoint``):

    PYTHONPATH=src python -m evaluation.score_predictions \\
        --predictions artifacts/same_evidence_b2/predictions.jsonl \\
        --run-sidecar artifacts/same_evidence_b2/run.json \\
        --output artifacts/same_evidence_b2/metrics.json

Rows still need ``label_gold`` (or ``gold_label`` / ``gold``). ``CONTRADICT``
gold is scored as REFUTE. Do not score a file that mixes mock and live rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

from evaluation.registry import get_formula
from evaluation.scorers import (
    ENDORSEMENT_LABEL,
    NATIVE_LABELS,
    PREDICTION_LABEL_SPACE,
    native_false_endorsement,
    normalize_native_label,
    precision_recall_f1,
    three_way_counts,
)

_PRED_KEYS = ("label_pred", "predicted_label", "label")
_GOLD_KEYS = ("label_gold", "gold_label", "gold")
_OK_EXECUTION = {"ok", "completed", "success"}
_NATIVE_FORMULA = "F-native-scifact"
_FE_FORMULA = "F-false-endorsement"


class ScoreError(Exception):
    """The predictions file cannot be scored."""

    def __init__(self, message: str, exit_code: int = 1) -> None:
        super().__init__(message)
        self.exit_code = exit_code


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ScoreError(f"predictions file not found: {path}")
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ScoreError(f"{path}:{line_number}: invalid JSON ({exc})") from exc
        if not isinstance(row, dict):
            raise ScoreError(f"{path}:{line_number}: expected a JSON object")
        claim_id = row.get("claim_id")
        if not isinstance(claim_id, str) or not claim_id.strip():
            raise ScoreError(f"{path}:{line_number}: claim_id must be a non-empty string")
        if claim_id in seen:
            raise ScoreError(f"{path}:{line_number}: duplicate claim_id {claim_id}")
        seen.add(claim_id)
        rows.append(row)
    if not rows:
        raise ScoreError(f"{path}: no prediction rows", exit_code=2)
    return rows


def _read_sidecar(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.is_file():
        raise ScoreError(f"run sidecar not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScoreError(f"{path}: invalid JSON ({exc})") from exc
    if not isinstance(payload, dict):
        raise ScoreError(f"{path}: expected a JSON object")
    return payload


def _sidecar_run_id(sidecar: Mapping[str, Any] | None) -> str | None:
    if not sidecar:
        return None
    run = sidecar.get("run")
    if isinstance(run, Mapping) and isinstance(run.get("run_id"), str) and run["run_id"].strip():
        return run["run_id"]
    if isinstance(sidecar.get("run_id"), str) and sidecar["run_id"].strip():
        return sidecar["run_id"]
    return None


def resolve_run_id(
    rows: Sequence[Mapping[str, Any]],
    *,
    cli_run_id: str | None,
    sidecar: Mapping[str, Any] | None,
) -> str:
    """Prefer the CLI flag, then the sidecar, then a single row run_id."""
    if cli_run_id is not None and cli_run_id.strip():
        return cli_run_id.strip()
    sidecar_id = _sidecar_run_id(sidecar)
    if sidecar_id:
        return sidecar_id
    found = {row["run_id"] for row in rows if isinstance(row.get("run_id"), str) and row["run_id"].strip()}
    if len(found) == 1:
        return next(iter(found))
    if len(found) > 1:
        raise ScoreError("predictions contain multiple run_id values; pass --run-id")
    raise ScoreError("run_id missing; pass --run-id or --run-sidecar", exit_code=2)


def _uniform_field(rows: Sequence[Mapping[str, Any]], key: str, *, what: str) -> str | None:
    values = {row[key] for row in rows if isinstance(row.get(key), str) and row[key].strip()}
    if len(values) > 1:
        raise ScoreError(f"mixed {what}: {sorted(values)}")
    if len(values) == 1:
        return next(iter(values))
    return None


def _method_id(rows: Sequence[Mapping[str, Any]]) -> str | None:
    method = _uniform_field(rows, "method_id", what="method_id")
    adaptation = _uniform_field(rows, "adaptation", what="adaptation")
    if method and adaptation and method != adaptation:
        raise ScoreError(f"method_id {method!r} does not match adaptation {adaptation!r}")
    return method or adaptation


def _execution_ok(row: Mapping[str, Any]) -> bool:
    if "execution_status" not in row or row["execution_status"] is None:
        return True
    status = row["execution_status"]
    if not isinstance(status, str):
        return False
    return status.strip().lower() in _OK_EXECUTION


def _predicted_label(row: Mapping[str, Any]) -> str | None:
    for key in _PRED_KEYS:
        if key in row and row[key] is not None:
            return normalize_native_label(row[key])
    return None


def _gold_label(row: Mapping[str, Any]) -> str | None:
    for key in _GOLD_KEYS:
        if key not in row or row[key] is None:
            continue
        return normalize_native_label(row[key])
    return None


def _metric(
    *,
    run_id: str,
    formula_id: str,
    metric: str,
    value: float,
    label: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record: dict[str, Any] = {
        "run_id": run_id,
        "formula_id": formula_id,
        "metric": metric,
        "class": label,
        "value": value,
        "notes_path": get_formula(formula_id).notes_path,
    }
    if extra:
        record.update(extra)
    return record


def score_prediction_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    run_id: str,
    inference_mode: str | None = None,
) -> dict[str, Any]:
    """Score in-memory B2 rows. ``run_id`` is copied onto every metric."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise ScoreError("run_id missing; pass --run-id or --run-sidecar", exit_code=2)

    mode = inference_mode if inference_mode is not None else _uniform_field(
        rows, "inference_mode", what="inference_mode"
    )
    if inference_mode is not None and inference_mode.strip():
        row_mode = _uniform_field(rows, "inference_mode", what="inference_mode")
        if row_mode is not None and row_mode != inference_mode:
            raise ScoreError(
                f"sidecar inference_mode {inference_mode!r} does not match rows ({row_mode!r})"
            )
        mode = inference_mode

    pairs: list[tuple[str, str]] = []
    skipped_unlabeled = 0
    skipped_not_ok = 0
    for row in rows:
        claim_id = row.get("claim_id", "<missing>")
        if not _execution_ok(row):
            skipped_not_ok += 1
            continue
        try:
            predicted = _predicted_label(row)
        except ValueError as exc:
            raise ScoreError(f"{claim_id}: {exc}") from exc
        if predicted is None:
            raise ScoreError(f"{claim_id}: missing predicted label ({', '.join(_PRED_KEYS)})")
        try:
            gold = _gold_label(row)
        except ValueError as exc:
            raise ScoreError(f"{claim_id}: {exc}") from exc
        if gold is None:
            skipped_unlabeled += 1
            continue
        pairs.append((gold, predicted))

    if not pairs:
        raise ScoreError(
            "no rows with gold labels to score; add label_gold "
            "(SUPPORT, REFUTE, or NEI; CONTRADICT counts as REFUTE). "
            "This scorer does not read the corpus.",
            exit_code=2,
        )

    counts = three_way_counts(pairs)
    metrics: list[dict[str, Any]] = []
    per_class_f1: list[float] = []
    per_class_p: list[float] = []
    per_class_r: list[float] = []
    micro_tp = micro_fp = micro_fn = 0
    for label in NATIVE_LABELS:
        tp = counts[label]["tp"]
        fp = counts[label]["fp"]
        fn = counts[label]["fn"]
        precision, recall, f1 = precision_recall_f1(tp, fp, fn)
        per_class_p.append(precision)
        per_class_r.append(recall)
        per_class_f1.append(f1)
        micro_tp += tp
        micro_fp += fp
        micro_fn += fn
        for name, value in (("precision", precision), ("recall", recall), ("f1", f1)):
            metrics.append(
                _metric(
                    run_id=run_id,
                    formula_id=_NATIVE_FORMULA,
                    metric=name,
                    value=value,
                    label=label,
                )
            )

    micro_p, micro_r, micro_f1 = precision_recall_f1(micro_tp, micro_fp, micro_fn)
    for name, value in (
        ("micro_precision", micro_p),
        ("micro_recall", micro_r),
        ("micro_f1", micro_f1),
    ):
        metrics.append(
            _metric(
                run_id=run_id,
                formula_id=_NATIVE_FORMULA,
                metric=name,
                value=value,
                label=None,
            )
        )

    n_classes = len(NATIVE_LABELS)
    macro_p = sum(per_class_p) / n_classes
    macro_r = sum(per_class_r) / n_classes
    macro_f1 = sum(per_class_f1) / n_classes
    for name, value in (
        ("macro_precision", macro_p),
        ("macro_recall", macro_r),
        ("macro_f1", macro_f1),
    ):
        metrics.append(
            _metric(
                run_id=run_id,
                formula_id=_NATIVE_FORMULA,
                metric=name,
                value=value,
                label=None,
            )
        )

    endorsement = native_false_endorsement(pairs)
    fe_extra = {
        "n_false_endorsements": endorsement["n_false_endorsements"],
        "n_gold_nonsupported": endorsement["n_gold_nonsupported"],
        "n_predicted_supported": endorsement["n_predicted_supported"],
        "endorsement_label": ENDORSEMENT_LABEL,
    }
    metrics.append(
        _metric(
            run_id=run_id,
            formula_id=_FE_FORMULA,
            metric="false_endorsement_gold_nonsup",
            value=endorsement["false_endorsement_gold_nonsup"],
            label=ENDORSEMENT_LABEL,
            extra={**fe_extra, "alias": "false_support_rate"},
        )
    )
    metrics.append(
        _metric(
            run_id=run_id,
            formula_id=_FE_FORMULA,
            metric="false_endorsement_pred_sup",
            value=endorsement["false_endorsement_pred_sup"],
            label=ENDORSEMENT_LABEL,
            extra={**fe_extra, "alias": "false_support_among_predicted_support"},
        )
    )

    return {
        "run_id": run_id,
        "method_id": _method_id(rows),
        "inference_mode": mode,
        "prediction_label_space": PREDICTION_LABEL_SPACE,
        "endorsement_label": ENDORSEMENT_LABEL,
        "n_rows": len(rows),
        "n_scored": len(pairs),
        "n_skipped_unlabeled": skipped_unlabeled,
        "n_skipped_not_ok": skipped_not_ok,
        "counts": {
            "run_id": run_id,
            "formula_id": _NATIVE_FORMULA,
            "notes_path": get_formula(_NATIVE_FORMULA).notes_path,
            "per_class": counts,
            "micro": {"tp": micro_tp, "fp": micro_fp, "fn": micro_fn},
        },
        "metrics": metrics,
    }


def score_predictions_file(
    predictions: Path,
    *,
    run_id: str | None = None,
    run_sidecar: Path | None = None,
) -> dict[str, Any]:
    rows = _read_jsonl(predictions)
    sidecar = _read_sidecar(run_sidecar)
    resolved = resolve_run_id(rows, cli_run_id=run_id, sidecar=sidecar)
    sidecar_mode = None
    if sidecar and isinstance(sidecar.get("inference_mode"), str):
        sidecar_mode = sidecar["inference_mode"]
    report = score_prediction_rows(rows, run_id=resolved, inference_mode=sidecar_mode)
    report["provenance"] = {
        "run_id": resolved,
        "predictions": str(predictions),
        "run_sidecar": str(run_sidecar) if run_sidecar else None,
    }
    return report


def dumps_metrics(report: Mapping[str, Any]) -> str:
    return json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Score B2 same-evidence predictions.jsonl "
            "(SUPPORT/REFUTE/NEI precision, recall, F1, and false endorsement)."
        )
    )
    parser.add_argument("--predictions", required=True, type=Path, help="predictions.jsonl path")
    parser.add_argument(
        "--run-sidecar",
        type=Path,
        default=None,
        help="run.json; run_id is read from run.run_id",
    )
    parser.add_argument("--run-id", default=None, help="overrides the sidecar and row run_id")
    parser.add_argument("--output", required=True, type=Path, help="metrics JSON path")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        report = score_predictions_file(
            args.predictions,
            run_id=args.run_id,
            run_sidecar=args.run_sidecar,
        )
    except ScoreError as exc:
        print(f"SCORE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(exc.exit_code) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(dumps_metrics(report), encoding="utf-8")
    print(
        f"wrote {args.output} run_id={report['run_id']} "
        f"n_scored={report['n_scored']} inference_mode={report['inference_mode']}"
    )


if __name__ == "__main__":
    main()
