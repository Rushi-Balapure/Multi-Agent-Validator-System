"""Calibration of the one condition that verbalises confidence.

The claim-visible judge (B1) emits a confidence with every verdict. This
script fits a single temperature on the **calibration split** (100 claims
reserved before any prompt work), then reports Brier score, negative
log-likelihood, and expected calibration error on the development and
held-out samples. No parameter is fitted on either of those samples.

It also writes the reliability bins used by the paper's reliability figure.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from evaluation.calibration import (  # noqa: E402
    ece,
    nll,
    verbalized_distribution,
)
from evaluation.score_predictions import score_predictions_file  # noqa: E402

TABLES = ROOT / "docs" / "paper-assets" / "tables"
PAPER_TABLES = ROOT / "paper" / "tables"
REGISTRY = TABLES / "run_registry.json"
TEMPERATURES = [round(0.1 * step, 1) for step in range(1, 101)]


def _native_gold(label: str) -> str:
    token = str(label).strip().upper()
    return "REFUTE" if token == "CONTRADICT" else token


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _rows_with_gold(predictions: Path, sidecar: Path, split: str) -> list[dict]:
    report = score_predictions_file(predictions, run_sidecar=sidecar, join_gold=split)
    gold_by_id = {
        item["claim_id"]: _native_gold(item["label_gold"])
        for item in (report.get("gold_join") or {}).get("claims") or []
        if item.get("label_gold")
    }
    rows = []
    for row in _read_jsonl(predictions):
        if str(row.get("execution_status") or "ok") != "ok":
            continue
        gold = gold_by_id.get(row["claim_id"])
        confidence = row.get("confidence")
        if not gold or not isinstance(confidence, (int, float)):
            continue
        rows.append(
            {
                "claim_id": row["claim_id"],
                "label": str(row.get("label")),
                "confidence": float(confidence),
                "gold": gold,
            }
        )
    return rows


def _probs(row: dict, temperature: float) -> list[float]:
    """Confidence is verbalised; temperature rescales the implied log-odds."""
    label = row["label"]
    confidence = row["confidence"]
    rest = max((1.0 - confidence) / 2.0, 1e-6)
    logits = []
    for candidate in ("SUPPORT", "REFUTE", "NEI"):
        if candidate == label:
            logits.append(confidence)
        else:
            logits.append(rest)
    scaled = [value / temperature for value in logits]
    peak = max(scaled)
    exps = [pow(2.718281828459045, value - peak) for value in scaled]
    total = sum(exps)
    return [value / total for value in exps]


def _fit_temperature(rows: list[dict]) -> tuple[float, float]:
    best = (1.0, float("inf"))
    for temperature in TEMPERATURES:
        probs = [_probs(row, temperature) for row in rows]
        golds = [row["gold"] for row in rows]
        value = nll(probs, golds)
        if value < best[1]:
            best = (temperature, value)
    return best


def _evaluate(rows: list[dict], temperature: float) -> dict:
    probs = [_probs(row, temperature) for row in rows]
    golds = [row["gold"] for row in rows]
    labels = ["SUPPORT", "REFUTE", "NEI"]
    bins: dict[int, dict] = {}
    for row, prob in zip(rows, probs, strict=True):
        index = labels.index(row["gold"])
        predicted = max(range(3), key=lambda i: prob[i])
        confidence = prob[predicted]
        correct = 1.0 if predicted == index else 0.0
        bucket = min(int(confidence * 10), 9)
        block = bins.setdefault(bucket, {"n": 0, "confidence": 0.0, "accuracy": 0.0})
        block["n"] += 1
        block["confidence"] += confidence
        block["accuracy"] += correct
    reliability = []
    for bucket, block in sorted(bins.items()):
        n = block["n"]
        reliability.append(
            {
                "bin": bucket,
                "n": n,
                "confidence": block["confidence"] / n,
                "accuracy": block["accuracy"] / n,
            }
        )
    return {
        "n": len(rows),
        "temperature": temperature,
        "brier": sum(
            sum((p - (1.0 if i == labels.index(row["gold"]) else 0.0)) ** 2 for i, p in enumerate(prob))
            for row, prob in zip(rows, probs, strict=True)
        )
        / max(len(rows), 1),
        "nll": nll(probs, golds),
        "ece": ece(probs, golds),
        "reliability": reliability,
    }


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    payload: dict[str, dict] = {}
    for family, family_spec in registry["families"].items():
        calibration_dir = family_spec.get("calibration")
        if not calibration_dir:
            continue
        if isinstance(calibration_dir, dict):
            calibration_dir = calibration_dir.get("B1")
        if not calibration_dir:
            continue
        calibration_predictions = ROOT / calibration_dir / "predictions.jsonl"
        calibration_sidecar = ROOT / calibration_dir / "run.json"
        if not calibration_predictions.is_file() or not calibration_sidecar.is_file():
            print(f"  skip {family}: no calibration-split run")
            continue
        fit_rows = _rows_with_gold(calibration_predictions, calibration_sidecar, "calibration")
        if not fit_rows:
            print(f"  skip {family}: calibration rows have no usable confidence")
            continue
        temperature, _ = _fit_temperature(fit_rows)
        payload[family] = {
            "calibration": _evaluate(fit_rows, temperature),
            "fitted_temperature": temperature,
            "fitted_on": "calibration",
        }
        for split_name, conditions in family_spec.items():
            if split_name in {"label", "calibration"}:
                continue
            directory = conditions.get("B1")
            if not directory:
                continue
            predictions = ROOT / directory / "predictions.jsonl"
            sidecar = ROOT / directory / "run.json"
            if not predictions.is_file() or not sidecar.is_file():
                continue
            split = registry["splits"][split_name]
            rows = _rows_with_gold(predictions, sidecar, split)
            if rows:
                payload[family][split_name] = _evaluate(rows, temperature)
    out = TABLES / "calibration_by_family.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        "Model family & Evaluation split & $n$ & Brier & NLL & ECE & temperature \\\\",
        "\\midrule",
    ]
    for family, block in payload.items():
        label = registry["families"][family].get("label", family)
        for split_name in ("calibration", "dev300", "heldout300"):
            entry = block.get(split_name)
            if not entry:
                continue
            lines.append(
                " & ".join(
                    [
                        label,
                        split_name,
                        str(entry["n"]),
                        f"{entry['brier']:.3f}",
                        f"{entry['nll']:.3f}",
                        f"{entry['ece']:.3f}",
                        f"{block['fitted_temperature']:.1f}",
                    ]
                )
                + " \\\\"
            )
        lines.append("\\addlinespace[2pt]")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    PAPER_TABLES.mkdir(parents=True, exist_ok=True)
    (PAPER_TABLES / "t4_calibration.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} and paper/tables/t4_calibration.tex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
