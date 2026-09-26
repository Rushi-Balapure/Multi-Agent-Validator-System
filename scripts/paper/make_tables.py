"""Build T1-T4 markdown tables from scored artifacts only."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "paper-assets" / "tables"
PLACEHOLDER = "—"


def _load(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _metric(report: dict | None, name: str) -> str:
    if not report:
        return PLACEHOLDER
    for item in report.get("metrics") or []:
        if item.get("metric") == name:
            return f"{item['value']:.3f}"
    return PLACEHOLDER


def _tokens(sidecar: dict | None) -> str:
    if not sidecar:
        return PLACEHOLDER
    run = sidecar.get("run") or {}
    tokens = run.get("tokens") or {}
    total = tokens.get("total_tokens")
    n = sidecar.get("n_predictions") or 1
    if total is None:
        return PLACEHOLDER
    return f"{total / n:.0f}"


def write_t1(b2, v, bootstrap) -> str:
    fe = PLACEHOLDER
    if bootstrap and bootstrap.get("paired_difference"):
        diff = bootstrap["paired_difference"]["false_endorsement_gold_nonsup"]
        fe = (
            f"{diff['point_estimate']:.3f} "
            f"[{diff['ci_low']:.3f}, {diff['ci_high']:.3f}]"
        )
    return f"""# T1 Main results (SciFact 3-way)

Primary metric is V versus B2 false endorsement on gold non-support.
Intervals are paired cluster bootstrap (2000 resamples) over cited-document families.

| Method | n | micro-F1 | macro-F1 | FE gold-nonsup | SUPPORT recall | fail-closed |
| --- | --- | --- | --- | --- | --- | --- |
| B2 | {(b2 or {}).get('n_scored', PLACEHOLDER)} | {_metric(b2, 'micro_f1')} | {_metric(b2, 'macro_f1')} | {_metric(b2, 'false_endorsement_gold_nonsup')} | {_class(b2, 'recall', 'SUPPORT')} | {(b2 or {}).get('n_skipped_not_ok', PLACEHOLDER)} |
| V | {(v or {}).get('n_scored', PLACEHOLDER)} | {_metric(v, 'micro_f1')} | {_metric(v, 'macro_f1')} | {_metric(v, 'false_endorsement_gold_nonsup')} | {_class(v, 'recall', 'SUPPORT')} | {(v or {}).get('n_skipped_not_ok', PLACEHOLDER)} |

Paired FE difference (V − B2): {fe}
"""


def _class(report: dict | None, metric: str, label: str) -> str:
    if not report:
        return PLACEHOLDER
    for item in report.get("metrics") or []:
        if item.get("metric") == metric and item.get("class") == label:
            return f"{item['value']:.3f}"
    return PLACEHOLDER


def write_t2(reports: dict[str, dict | None]) -> str:
    lines = [
        "# T2 2x2 ablation (evidence access × reading policy)",
        "",
        "| Cell | evidence | reading | micro-F1 | FE gold-nonsup |",
        "| --- | --- | --- | --- | --- |",
    ]
    cells = (
        ("B1", "D0", "claim-visible"),
        ("B2", "D0", "neutral/evidence-first"),
        ("B3", "D1", "claim-visible"),
        ("V-D1", "D1", "neutral/evidence-first"),
        ("V", "D0∪D1", "reconciled"),
        ("B0", "none", "prior knowledge"),
        ("O", "gold rationales", "claim-visible"),
    )
    for name, evidence, reading in cells:
        report = reports.get(name)
        lines.append(
            f"| {name} | {evidence} | {reading} | {_metric(report, 'micro_f1')} | "
            f"{_metric(report, 'false_endorsement_gold_nonsup')} |"
        )
    return "\n".join(lines) + "\n"


def write_t3(sidecars: dict[str, dict | None]) -> str:
    lines = [
        "# T3 Cost and latency",
        "",
        "| Method | tokens/claim | estimated USD | n_calls |",
        "| --- | --- | --- | --- |",
    ]
    for name, sidecar in sidecars.items():
        tokens = _tokens(sidecar)
        cost = PLACEHOLDER
        n_calls = PLACEHOLDER
        if sidecar:
            usage = (sidecar.get("run") or {}).get("tokens") or {}
            if usage.get("estimated_cost_usd") is not None:
                cost = f"{usage['estimated_cost_usd']:.4f}"
            if usage.get("n_calls") is not None:
                n_calls = str(usage["n_calls"])
        lines.append(f"| {name} | {tokens} | {cost} | {n_calls} |")
    return "\n".join(lines) + "\n"


def write_t4(calib: dict | None) -> str:
    if not calib:
        body = "| split | Brier | NLL | ECE | temperature |\n| --- | --- | --- | --- | --- |\n| — | — | — | — | — |\n"
    else:
        body = (
            "| split | Brier | NLL | ECE | temperature |\n| --- | --- | --- | --- | --- |\n"
            f"| {calib.get('split', '—')} | {calib.get('brier', '—')} | "
            f"{calib.get('nll', '—')} | {calib.get('ece', '—')} | "
            f"{calib.get('temperature', '—')} |\n"
        )
    return "# T4 Calibration\n\n" + body


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    comparison = _load(OUT / "dev300_b2_vs_v.json")
    b2 = (comparison or {}).get("b2") or _load(OUT / "b2_dev300_metrics.json")
    v = (comparison or {}).get("v") or _load(OUT / "v_dev300_metrics.json")
    bootstrap = (comparison or {}).get("bootstrap")
    (OUT / "T1_main.md").write_text(write_t1(b2, v, bootstrap), encoding="utf-8")
    reports = {
        "B2": b2,
        "V": v,
        "B0": _load(OUT / "b0_dev300_metrics.json"),
        "B1": _load(OUT / "b1_dev300_metrics.json"),
        "B3": _load(OUT / "b3_dev300_metrics.json"),
        "V-D1": _load(OUT / "vd1_dev300_metrics.json"),
        "O": _load(OUT / "oracle_dev300_metrics.json"),
    }
    (OUT / "T2_ablation.md").write_text(write_t2(reports), encoding="utf-8")
    sidecars = {
        "B2": _load(ROOT / "artifacts" / "same_evidence_b2_dev300" / "run.json"),
        "V": _load(ROOT / "artifacts" / "validator_v_dev300" / "run.json"),
    }
    (OUT / "T3_cost.md").write_text(write_t3(sidecars), encoding="utf-8")
    (OUT / "T4_calibration.md").write_text(write_t4(_load(OUT / "calibration.json")), encoding="utf-8")
    print(f"wrote tables under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
