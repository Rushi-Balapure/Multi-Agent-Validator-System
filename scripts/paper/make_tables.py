"""Score every registered run and write the paper's tables.

The registry (``docs/paper-assets/tables/run_registry.json``) lists the
artifact directory of each condition for each model family and evaluation
split. This script scores those prediction files with the repository's own
metric code, derives the V-D1 ablation cell from the V predictions, runs the
preregistered paired cluster bootstrap for V versus B2, and writes

* scored metric JSON files under ``docs/paper-assets/tables/`` (checked in),
* LaTeX table fragments under ``paper/tables/`` (included by ``paper/main.tex``).

It never edits a prediction file and never fits anything on test data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from evaluation.compare_runs import compare  # noqa: E402
from evaluation.score_predictions import score_predictions_file  # noqa: E402
from validator.baselines.extract_vd1 import extract_vd1_file  # noqa: E402

TABLES = ROOT / "docs" / "paper-assets" / "tables"
PAPER_TABLES = ROOT / "paper" / "tables"
REGISTRY = TABLES / "run_registry.json"

CONDITION_LABELS = {
    "B0": "B0 (prior knowledge)",
    "B1": "B1 (D0, claim-visible)",
    "B2": "B2 (D0, evidence-first)",
    "B3": "B3 (D1, claim-visible)",
    "V-D1": "V-D1 (D1, evidence-first)",
    "V": "V (D0 $\\cup$ D1, reconciled)",
    "O": "O (gold rationales)",
}
CONDITION_ORDER = ["B0", "B1", "B2", "B3", "V-D1", "V", "O"]
FAMILY_ORDER = ["gpt-6-luna", "minimax-m3.1-flash"]
SPLIT_ORDER = ["dev300", "heldout300"]


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _metric(report: dict | None, name: str) -> float | None:
    if not report:
        return None
    for item in report.get("metrics") or []:
        if item.get("metric") == name and item.get("class") is None:
            return float(item["value"])
    for item in report.get("metrics") or []:
        if item.get("metric") == name:
            return float(item["value"])
    return None


def _class_metric(report: dict | None, metric: str, label: str) -> float | None:
    if not report:
        return None
    for item in report.get("metrics") or []:
        if item.get("metric") == metric and item.get("class") == label:
            return float(item["value"])
    return None


def _fmt(value: float | None, digits: int = 3) -> str:
    if value is None:
        return "---"
    return f"{value:.{digits}f}"


def _ci(block: dict | None, digits: int = 3) -> str:
    if not block:
        return "---"
    return (
        f"{block['point_estimate']:.{digits}f} "
        f"[{block['ci_low']:.{digits}f}, {block['ci_high']:.{digits}f}]"
    )


def load_registry() -> dict:
    return _read_json(REGISTRY)


def score_registry(registry: dict) -> dict:
    """Score every registered condition. Returns {family: {split: {condition: report}}}."""
    scored: dict[str, dict[str, dict[str, Any]]] = {}
    for family, family_spec in registry["families"].items():
        scored[family] = {}
        for split_name, conditions in family_spec.items():
            if split_name == "label":
                continue
            split = registry["splits"][split_name]
            scored[family][split_name] = {}
            for condition, directory in conditions.items():
                directory_path = ROOT / directory
                predictions = directory_path / "predictions.jsonl"
                sidecar = directory_path / "run.json"
                if not predictions.is_file():
                    print(f"  skip {family}/{split_name}/{condition}: no predictions file")
                    continue
                if not sidecar.is_file():
                    print(
                        f"  skip {family}/{split_name}/{condition}: run is unfinished "
                        "(no run sidecar yet)"
                    )
                    continue
                report = score_predictions_file(
                    predictions, run_sidecar=sidecar, join_gold=split
                )
                scored[family][split_name][condition] = report
                _write_json(TABLES / f"{family}_{split_name}_{condition}_metrics.json", report)
    return scored


def derive_vd1(registry: dict, scored: dict) -> None:
    """V-D1 is the D1 arm of the V run. It is a mapping, not a new model run."""
    for family, family_spec in registry["families"].items():
        for split_name, conditions in family_spec.items():
            if split_name == "label":
                continue
            v_dir = ROOT / conditions.get("V", "")
            predictions = v_dir / "predictions.jsonl"
            sidecar = v_dir / "run.json"
            if not predictions.is_file() or not sidecar.is_file():
                continue
            derived = v_dir / "predictions_vd1.jsonl"
            rows = extract_vd1_file(predictions, derived)
            split = registry["splits"][split_name]
            report = score_predictions_file(
                derived, run_sidecar=sidecar, join_gold=split
            )
            report["derived_from"] = str(predictions.relative_to(ROOT))
            report["n_rows_derived"] = len(rows)
            scored[family][split_name]["V-D1"] = report
            _write_json(TABLES / f"{family}_{split_name}_V-D1_metrics.json", report)


def bootstrap_pairs(registry: dict) -> dict:
    """Paired cluster bootstrap for V versus B2 in every family and split."""
    results: dict[str, dict[str, Any]] = {}
    for family, family_spec in registry["families"].items():
        results[family] = {}
        for split_name, conditions in family_spec.items():
            if split_name == "label":
                continue
            b2_dir = ROOT / conditions.get("B2", "")
            v_dir = ROOT / conditions.get("V", "")
            if not (b2_dir / "predictions.jsonl").is_file():
                continue
            if not (v_dir / "predictions.jsonl").is_file():
                continue
            if not (b2_dir / "run.json").is_file() or not (v_dir / "run.json").is_file():
                print(f"  skip bootstrap {family}/{split_name}: run is unfinished")
                continue
            split = registry["splits"][split_name]
            report = compare(
                b2_predictions=b2_dir / "predictions.jsonl",
                v_predictions=v_dir / "predictions.jsonl",
                b2_sidecar=b2_dir / "run.json",
                v_sidecar=v_dir / "run.json",
                split=split,
            )
            results[family][split_name] = report
            _write_json(TABLES / f"{family}_{split_name}_b2_vs_v.json", report)
    return results


def _condition_rows(
    family: str,
    split_name: str,
    scored: dict,
) -> list[tuple[str, dict]]:
    reports = scored.get(family, {}).get(split_name, {})
    rows = []
    for condition in CONDITION_ORDER:
        if condition in reports:
            rows.append((condition, reports[condition]))
    return rows


def _write(name: str, body: str) -> None:
    PAPER_TABLES.mkdir(parents=True, exist_ok=True)
    (PAPER_TABLES / name).write_text(body, encoding="utf-8")


def write_main_table(scored: dict, boots: dict, split_name: str) -> None:
    lines = [
        "\\begin{tabular}{lrrrrrr}",
        "\\toprule",
        "Model family & Method & $n$ scored & micro-F1 & macro-F1 & FE (gold non-sup) & SUPPORT recall \\\\",
        "\\midrule",
    ]
    for family in FAMILY_ORDER:
        rows = _condition_rows(family, split_name, scored)
        if not rows:
            continue
        label = registry_label(family)
        for index, (condition, report) in enumerate(rows):
            values = [
                label if index == 0 else "",
                CONDITION_LABELS[condition],
                str(report.get("n_scored", "---")),
                _fmt(_metric(report, "micro_f1")),
                _fmt(_metric(report, "macro_f1")),
                _fmt(_metric(report, "false_endorsement_gold_nonsup")),
                _fmt(_class_metric(report, "recall", "SUPPORT")),
            ]
            lines.append(" & ".join(values) + " \\\\")
            if condition == "B2":
                lines.append("\\addlinespace[2pt]")
        lines.append("\\midrule")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write(f"t1_{split_name}.tex", "\n".join(lines) + "\n")


def registry_label(family: str) -> str:
    registry = load_registry()
    return str(registry["families"][family].get("label", family))


def write_paired_table(boots: dict, split_name: str) -> None:
    lines = [
        "\\begin{tabular}{llrrrlr}",
        "\\toprule",
        "Model family & Comparison & FE difference & 95\\% CI & $p$ (bootstrap) & excl.\\ 0 & $n$ paired \\\\",
        "\\midrule",
    ]
    for family in FAMILY_ORDER:
        report = boots.get(family, {}).get(split_name)
        if not report:
            continue
        bootstrap = report.get("bootstrap") or {}
        diff = (bootstrap.get("paired_difference") or {}).get("false_endorsement_gold_nonsup")
        n_paired = bootstrap.get("n_claims_paired")
        excludes = (diff or {}).get("excludes_zero")
        p_text = "---" if not diff else f"{float(diff['p_raw']):.2f}"
        lines.append(
            " & ".join(
                [
                    registry_label(family),
                    "V $-$ B2",
                    _fmt((diff or {}).get("point_estimate")) if diff else "---",
                    _ci(diff),
                    p_text,
                    "yes" if excludes else "no",
                    str(n_paired if n_paired is not None else "---"),
                ]
            )
            + " \\\\"
        )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write(f"t1b_{split_name}_paired.tex", "\n".join(lines) + "\n")


def write_ablation_table(scored: dict) -> None:
    lines = [
        "\\begin{tabular}{llrrrr}",
        "\\toprule",
        "Model family & Cell & Evidence & Reading policy & micro-F1 & FE (gold non-sup) \\\\",
        "\\midrule",
    ]
    cells = {
        "B1": ("D0", "claim-visible"),
        "B2": ("D0", "neutral / evidence-first"),
        "B3": ("D1", "claim-visible"),
        "V-D1": ("D1", "neutral / evidence-first"),
        "V": ("D0 $\\cup$ D1", "reconciled"),
        "B0": ("none", "prior knowledge"),
        "O": ("gold rationales", "claim-visible"),
    }
    for family in FAMILY_ORDER:
        reports = scored.get(family, {}).get("dev300", {})
        for condition in CONDITION_ORDER:
            report = reports.get(condition)
            if not report:
                continue
            evidence, reading = cells[condition]
            lines.append(
                " & ".join(
                    [
                        registry_label(family),
                        condition,
                        evidence,
                        reading,
                        _fmt(_metric(report, "micro_f1")),
                        _fmt(_metric(report, "false_endorsement_gold_nonsup")),
                    ]
                )
                + " \\\\"
            )
        lines.append("\\addlinespace[2pt]")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t2_ablation.tex", "\n".join(lines) + "\n")


def write_cost_table(registry: dict) -> None:
    lines = [
        "\\begin{tabular}{lllrrrrr}",
        "\\toprule",
        "Model family & Split & Method & tokens / claim & calls / claim & median latency (s) & p95 latency (s) \\\\",
        "\\midrule",
    ]
    for family in FAMILY_ORDER:
        for split_name, conditions in registry["families"][family].items():
            if split_name == "label":
                continue
            for condition in CONDITION_ORDER:
                directory = conditions.get(condition)
                if not directory:
                    continue
                sidecar_path = ROOT / directory / "run.json"
                if not sidecar_path.is_file():
                    continue
                sidecar = _read_json(sidecar_path)
                run = sidecar.get("run") or {}
                usage = run.get("tokens") or {}
                latency = usage.get("latency_seconds") or {}
                n = sidecar.get("n_predictions")
                if n is None:
                    run_id = str(run.get("run_id", ""))
                    n = int(run_id.split("-n")[-1].split("-")[0]) if "-n" in run_id else 1
                n = int(n)
                tokens_per_claim = (usage.get("total_tokens") or 0) / max(n, 1)
                calls_per_claim = (usage.get("n_calls") or 0) / max(n, 1)
                lines.append(
                    " & ".join(
                        [
                            registry_label(family),
                            split_name,
                            condition,
                            f"{tokens_per_claim:,.0f}",
                            f"{calls_per_claim:.2f}",
                            _fmt(latency.get("median"), 1),
                            _fmt(latency.get("p95"), 1),
                        ]
                    )
                    + " \\\\"
                )
            lines.append("\\addlinespace[2pt]")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t3_cost.tex", "\n".join(lines) + "\n")


def write_confusion_table(scored: dict) -> None:
    lines = [
        "\\begin{tabular}{llrrrrrrr}",
        "\\toprule",
        "Model family & Method & class & P & R & F1 & TP & FP & FN \\\\",
        "\\midrule",
    ]
    for family in FAMILY_ORDER:
        for condition in ("B2", "V"):
            report = scored.get(family, {}).get("dev300", {}).get(condition)
            if not report:
                continue
            counts = (report.get("counts") or {}).get("per_class") or {}
            for label in ("SUPPORT", "REFUTE", "NEI"):
                block = counts.get(label) or {}
                lines.append(
                    " & ".join(
                        [
                            registry_label(family),
                            condition,
                            label,
                            _fmt(_class_metric(report, "precision", label)),
                            _fmt(_class_metric(report, "recall", label)),
                            _fmt(_class_metric(report, "f1", label)),
                            str(block.get("tp", "---")),
                            str(block.get("fp", "---")),
                            str(block.get("fn", "---")),
                        ]
                    )
                    + " \\\\"
                )
            lines.append("\\addlinespace[2pt]")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t7_per_class.tex", "\n".join(lines) + "\n")


def _tex_name(name: str) -> str:
    """LaTeX control-sequence names must not contain digits.

    ``\\newcommand`` with a digit in the name fails with "Missing
    \\begin{document}" on this TeX Live, so digits are spelled out.
    """
    digits = {
        "0": "Zero",
        "1": "One",
        "2": "Two",
        "3": "Three",
        "4": "Four",
        "5": "Five",
        "6": "Six",
        "7": "Seven",
        "8": "Eight",
        "9": "Nine",
    }
    return "".join(digits.get(character, character) for character in name)


def write_macros(scored: dict, boots: dict) -> None:
    """Macros keep the prose numbers tied to the scored artifacts."""
    lines = ["% Generated by scripts/paper/make_tables.py. Do not edit by hand."]

    def macro(name: str, value: str) -> None:
        lines.append(f"\\newcommand{{\\{_tex_name(name)}}}{{{value}}}")

    for family in FAMILY_ORDER:
        tag = "luna" if family == "gpt-6-luna" else "mm"
        for split_name, split_tag in (("dev300", "dev"), ("heldout300", "held")):
            reports = scored.get(family, {}).get(split_name, {})
            for condition in CONDITION_ORDER:
                report = reports.get(condition)
                if not report:
                    continue
                prefix = f"{tag}{split_tag}{condition.replace('-', '')}"
                macro(f"{prefix}n", str(report.get("n_scored", 0)))
                macro(f"{prefix}microF1", _fmt(_metric(report, "micro_f1")))
                macro(f"{prefix}macroF1", _fmt(_metric(report, "macro_f1")))
                macro(
                    f"{prefix}fe",
                    _fmt(_metric(report, "false_endorsement_gold_nonsup")),
                )
                macro(
                    f"{prefix}supportRecall",
                    _fmt(_class_metric(report, "recall", "SUPPORT")),
                )
                macro(f"{prefix}failclosed", str(report.get("n_skipped_not_ok", 0)))
            bootstrap = boots.get(family, {}).get(split_name)
            if bootstrap:
                diff = (bootstrap.get("bootstrap") or {}).get("paired_difference", {}).get(
                    "false_endorsement_gold_nonsup"
                )
                if diff:
                    macro(f"{tag}{split_tag}fediff", _fmt(diff.get("point_estimate")))
                    macro(
                        f"{tag}{split_tag}feci",
                        f"[{diff['ci_low']:.3f}, {diff['ci_high']:.3f}]",
                    )
                macro(
                    f"{tag}{split_tag}npaired",
                    str((bootstrap.get("bootstrap") or {}).get("n_claims_paired", "---")),
                )
                macro(
                    f"{tag}{split_tag}nfamilies",
                    str(bootstrap.get("n_families", "---")),
                )
    _write("macros.tex", "\n".join(lines) + "\n")


def write_retrieval_table() -> None:
    path = TABLES / "retrieval_metrics.json"
    if not path.is_file():
        _write(
            "t5_retrieval.tex",
            "\\begin{tabular}{lr}\\toprule\\n(missing: run scripts/paper/make_retrieval_metrics.py)\\bottomrule\\n\\end{tabular}\n",
        )
        return
    payload = _read_json(path)
    micro = payload.get("micro") or {}
    n_docs = micro.get("n_retrieved_documents") or 0
    rows = [
        ("Claims scored", str(payload.get("n_claims", "---"))),
        ("Claims with annotated evidence", str(payload.get("n_claims_with_annotated_evidence", "---"))),
        ("Passages retrieved per claim ($k$)", str(payload.get("k", "---"))),
        ("Recall@$k$ (annotated documents found)", f"{payload.get('recall_at_k', 0):.3f}"),
        ("Precision@$k$ (retrieved documents annotated)", f"{payload.get('precision_at_k', 0):.3f}"),
        ("Overlap with $D_0$ (retrieved documents also cited)", f"{payload.get('d0_overlap', 0):.3f}"),
        ("Unique yield (annotated found but not cited)", f"{payload.get('unique_yield', 0):.3f}"),
        ("Refuting yield (contradicting documents found)", f"{payload.get('refuting_yield', 0):.3f}"),
        ("Unjudged rate (no annotation)", f"{payload.get('unjudged_rate', 0):.3f}"),
        ("Retrieved documents", str(n_docs)),
        (
            "Annotated documents retrieved that were not cited",
            f"{micro.get('n_annotated_retrieved_not_cited', 0)}",
        ),
    ]
    lines = [
        "\\begin{tabular}{lr}",
        "\\toprule",
        "Quantity & Value \\\\",
        "\\midrule",
    ]
    for name, value in rows:
        lines.append(f"{name} & {value} \\\\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t5_retrieval.tex", "\n".join(lines) + "\n")


def write_sensitivity_table(registry: dict) -> None:
    """Both fail-closed accountings for the primary comparison.

    ``scored``      execution failures are excluded from the metrics.
    ``all rows``    execution failures are scored with the label the method
                    recorded for them, which is the conservative NEI for every
                    fail-closed path here, so every submitted item counts.
    """
    lines = [
        "\\begin{tabular}{llrrrrr}",
        "\\toprule",
        "Model family & Method & accounting & $n$ scored & micro-F1 & FE (gold non-sup) & SUPPORT recall \\\\",
        "\\midrule",
    ]
    for family in FAMILY_ORDER:
        for split_name, conditions in registry["families"][family].items():
            if split_name in {"label", "calibration"}:
                continue
            split = registry["splits"][split_name]
            for condition in ("B2", "V"):
                directory = conditions.get(condition)
                if not directory:
                    continue
                predictions = ROOT / directory / "predictions.jsonl"
                sidecar = ROOT / directory / "run.json"
                if not predictions.is_file() or not sidecar.is_file():
                    continue
                for include_failed in (False, True):
                    report = score_predictions_file(
                        predictions,
                        run_sidecar=sidecar,
                        join_gold=split,
                        include_failed=include_failed,
                    )
                    accounting = "all rows" if include_failed else "scored only"
                    lines.append(
                        " & ".join(
                            [
                                registry_label(family),
                                f"{condition} ({split_name})",
                                accounting,
                                str(report.get("n_scored", "---")),
                                _fmt(_metric(report, "micro_f1")),
                                _fmt(_metric(report, "false_endorsement_gold_nonsup")),
                                _fmt(_class_metric(report, "recall", "SUPPORT")),
                            ]
                        )
                        + " \\\\"
                    )
        lines.append("\\addlinespace[2pt]")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t1c_sensitivity.tex", "\n".join(lines) + "\n")


def main() -> int:
    registry = load_registry()
    print("scoring registered runs")
    scored = score_registry(registry)
    print("deriving V-D1 cells")
    derive_vd1(registry, scored)
    print("paired bootstrap")
    boots = bootstrap_pairs(registry)
    print("writing LaTeX tables")
    write_main_table(scored, boots, "dev300")
    write_main_table(scored, boots, "heldout300")
    write_paired_table(boots, "dev300")
    write_paired_table(boots, "heldout300")
    write_ablation_table(scored)
    write_cost_table(registry)
    write_confusion_table(scored)
    write_retrieval_table()
    write_sensitivity_table(registry)
    write_macros(scored, boots)
    print(f"wrote tables under {PAPER_TABLES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
