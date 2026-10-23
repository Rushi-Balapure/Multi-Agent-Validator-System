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
    "B0": "B0",
    "B1": "B1",
    "B2": "B2",
    "B3": "B3",
    "V-D1": "V-D1",
    "V": "V",
    "O": "O",
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
    """The interval alone; the point estimate already has its own column."""
    if not block:
        return "---"
    return f"[{block['ci_low']:.{digits}f}, {block['ci_high']:.{digits}f}]"


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
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}lrrrrr@{}}",
        "\\toprule",
        "Method & $n$ & micro-F1 & macro-F1 & FE & SUPPORT R \\\\",
        "\\midrule",
    ]
    first = True
    for family in FAMILY_ORDER:
        rows = _condition_rows(family, split_name, scored)
        if not rows:
            continue
        if not first:
            lines.append("\\midrule")
        first = False
        label = registry_label(family)
        lines.append(
            f"\\multicolumn{{6}}{{@{{}}l}}{{\\emph{{{label}}}}} \\\\[1pt]"
        )
        for condition, report in rows:
            values = [
                CONDITION_LABELS[condition],
                str(report.get("n_scored", "---")),
                _fmt(_metric(report, "micro_f1")),
                _fmt(_metric(report, "macro_f1")),
                _fmt(_metric(report, "false_endorsement_gold_nonsup")),
                _fmt(_class_metric(report, "recall", "SUPPORT")),
            ]
            lines.append(" & ".join(values) + " \\\\")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write(f"t1_{split_name}.tex", "\n".join(lines) + "\n")


def registry_label(family: str) -> str:
    registry = load_registry()
    return str(registry["families"][family].get("label", family))


def write_paired_table(boots: dict, split_name: str) -> None:
    lines = [
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}lrrrrr@{}}",
        "\\toprule",
        "Method & $\\Delta$FE & 95\\% CI & $p$ & Excludes 0 & $n$ paired \\\\",
        "\\midrule",
    ]
    first = True
    for family in FAMILY_ORDER:
        report = boots.get(family, {}).get(split_name)
        if not report:
            continue
        bootstrap = report.get("bootstrap") or {}
        diff = (bootstrap.get("paired_difference") or {}).get("false_endorsement_gold_nonsup")
        n_paired = bootstrap.get("n_claims_paired")
        excludes = (diff or {}).get("excludes_zero")
        p_text = "---" if not diff else f"{float(diff['p_raw']):.2f}"
        if not first:
            lines.append("\\midrule")
        first = False
        lines.append(
            "\\multicolumn{6}{@{}l}{\\emph{"
            + registry_label(family)
            + "}} \\\\[1pt]"
        )
        lines.append(
            " & ".join(
                [
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
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}llrrr@{}}",
        "\\toprule",
        "Cell & Evidence & Reading policy & micro-F1 & FE \\\\",
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
    first = True
    for family in FAMILY_ORDER:
        reports = scored.get(family, {}).get("dev300", {})
        present = [c for c in CONDITION_ORDER if reports.get(c)]
        if not present:
            continue
        if not first:
            lines.append("\\midrule")
        first = False
        lines.append(
            "\\multicolumn{5}{@{}l}{\\emph{"
            + registry_label(family)
            + "}} \\\\[1pt]"
        )
        for condition in present:
            report = reports[condition]
            evidence, reading = cells[condition]
            lines.append(
                " & ".join(
                    [
                        condition,
                        evidence,
                        reading,
                        _fmt(_metric(report, "micro_f1")),
                        _fmt(_metric(report, "false_endorsement_gold_nonsup")),
                    ]
                )
                + " \\\\"
            )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t2_ablation.tex", "\n".join(lines) + "\n")


CALLS_PER_CLAIM = {
    "B0": 1,
    "B1": 1,
    "B2": 2,
    "B3": 1,
    "V-D1": 2,
    "V": 3,
    "O": 1,
}

# Below this many recorded calls, a per-call average is too noisy to print.
MIN_CALLS_FOR_COST = 100


def measured_costs(registry: dict) -> dict[tuple[str, str], tuple[str, int, int, dict]]:
    """Per-condition call counts and token totals, keyed by (family, condition).

    A resumed run keeps only the usage meter of its last invocation, so this
    picks, for each condition, the split that recorded the most calls, and
    discards measurements below ``MIN_CALLS_FOR_COST``.
    """
    measured: dict[tuple[str, str], tuple[str, int, int, dict]] = {}
    for family in FAMILY_ORDER:
        tag = "luna" if family == "gpt-6-luna" else "minimax"
        for condition in CONDITION_ORDER:
            if condition == "B0":
                continue
            best: tuple[str, int, int, dict] | None = None
            if tag == "luna":
                for split_name, conditions in registry["families"][family].items():
                    if split_name == "label":
                        continue
                    directory = conditions.get(condition)
                    if not directory:
                        continue
                    sidecar_path = ROOT / directory / "run.json"
                    if not sidecar_path.is_file():
                        continue
                    usage = (_read_json(sidecar_path).get("run") or {}).get("tokens") or {}
                    n_calls = int(usage.get("n_calls") or 0)
                    if n_calls < MIN_CALLS_FOR_COST:
                        continue
                    source = (
                        "dev"
                        if split_name == "dev300"
                        else ("held" if split_name == "heldout300" else split_name)
                    )
                    candidate = (
                        source,
                        n_calls,
                        int(usage.get("total_tokens") or 0),
                        usage.get("latency_seconds") or {},
                    )
                    if best is None or candidate[1] > best[1]:
                        best = candidate
            else:
                if condition not in ("B2", "V"):
                    continue
                sidecar_path = (
                    ROOT / "artifacts" / "cost_probe" / tag / condition / "run.json"
                )
                if sidecar_path.is_file():
                    usage = (_read_json(sidecar_path).get("run") or {}).get("tokens") or {}
                    n_calls = int(usage.get("n_calls") or 0)
                    if n_calls > 0:
                        best = (
                            "probe",
                            n_calls,
                            int(usage.get("total_tokens") or 0),
                            usage.get("latency_seconds") or {},
                        )
            if best is not None:
                measured[(family, condition)] = best
    return measured


def write_cost_table(registry: dict) -> None:
    """Model calls, per-call size, and latency.

    Per-call averages survive a resumed run; per-claim token totals do not,
    because every invocation writes its own usage meter. The table therefore
    reports calls per claim (a property of the design) next to the measured
    tokens per call, and the caption says how to read the product. B0 makes a
    single batch call for the whole sample, so it has no per-claim row.
    """
    measured = measured_costs(registry)
    lines = [
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}llrrrr@{}}",
        "\\toprule",
        "Method & measured on & calls/claim & tokens/call & median (s) & p95 (s) \\\\",
        "\\midrule",
    ]
    first = True
    for family in FAMILY_ORDER:
        blocks = [
            (condition,) + measured[(family, condition)]
            for condition in CONDITION_ORDER
            if (family, condition) in measured
        ]
        if not blocks:
            continue
        if not first:
            lines.append("\\midrule")
        first = False
        label = registry_label(family)
        if family != "gpt-6-luna":
            label += " (50-claim probe)"
        lines.append(
            "\\multicolumn{6}{@{}l}{\\emph{" + label + "}} \\\\[1pt]"
        )
        for condition, source, n_calls, total_tokens, latency in blocks:
            tokens_per_call = total_tokens / max(n_calls, 1)
            lines.append(
                " & ".join(
                    [
                        condition,
                        source,
                        f"{CALLS_PER_CLAIM[condition]:.0f}",
                        f"{tokens_per_call:,.0f}",
                        _fmt(latency.get("median"), 1),
                        _fmt(latency.get("p95"), 1),
                    ]
                )
                + " \\\\"
            )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t3_cost.tex", "\n".join(lines) + "\n")


def write_confusion_table(scored: dict) -> None:
    lines = [
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}llrrrrrr@{}}",
        "\\toprule",
        "Method & class & P & R & F1 & TP & FP & FN \\\\",
        "\\midrule",
    ]
    first = True
    for family in FAMILY_ORDER:
        blocks = []
        for condition in ("B2", "V"):
            report = scored.get(family, {}).get("dev300", {}).get(condition)
            if not report:
                continue
            counts = (report.get("counts") or {}).get("per_class") or {}
            for label in ("SUPPORT", "REFUTE", "NEI"):
                block = counts.get(label) or {}
                blocks.append(
                    " & ".join(
                        [
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
            blocks.append("\\addlinespace[1pt]")
        if not blocks:
            continue
        if not first:
            lines.append("\\midrule")
        first = False
        lines.append(
            "\\multicolumn{8}{@{}l}{\\emph{"
            + registry_label(family)
            + "}} \\\\[1pt]"
        )
        lines.extend(blocks)
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


def write_macros(scored: dict, boots: dict, registry: dict, extra: dict[str, str] | None = None) -> None:
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
                macro(
                    f"{prefix}supportPrecision",
                    _fmt(_class_metric(report, "precision", "SUPPORT")),
                )
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

    # All-rows (fail-closed scored as recorded) variants for B2 and V.
    for family in FAMILY_ORDER:
        tag = "luna" if family == "gpt-6-luna" else "mm"
        for split_name, split_tag in (("dev300", "dev"), ("heldout300", "held")):
            conditions = registry["families"][family].get(split_name, {})
            split = registry["splits"][split_name]
            for condition in ("B2", "V"):
                directory = conditions.get(condition)
                if not directory:
                    continue
                predictions = ROOT / directory / "predictions.jsonl"
                sidecar = ROOT / directory / "run.json"
                if not predictions.is_file() or not sidecar.is_file():
                    continue
                report = score_predictions_file(
                    predictions,
                    run_sidecar=sidecar,
                    join_gold=split,
                    include_failed=True,
                )
                prefix = f"{tag}{split_tag}{condition.replace('-', '')}allrows"
                macro(f"{prefix}n", str(report.get("n_scored", 0)))
                macro(f"{prefix}microF1", _fmt(_metric(report, "micro_f1")))
                macro(f"{prefix}fe", _fmt(_metric(report, "false_endorsement_gold_nonsup")))
                macro(
                    f"{prefix}supportRecall",
                    _fmt(_class_metric(report, "recall", "SUPPORT")),
                )

    # Retrieval-metric macros, quoted in the evidence-acquisition section.
    retrieval_path = TABLES / "retrieval_metrics.json"
    if retrieval_path.is_file():
        payload = _read_json(retrieval_path)
        macro("retrievalRecall", f"{payload.get('recall_at_k', 0):.2f}")
        macro("retrievalPrecision", f"{payload.get('precision_at_k', 0):.2f}")
        macro("retrievalOverlap", f"{payload.get('d0_overlap', 0):.2f}")
        macro("retrievalUnique", f"{payload.get('unique_yield', 0):.2f}")
        macro("retrievalUnjudged", f"{100 * payload.get('unjudged_rate', 0):.0f}")
        macro("retrievalRefuting", f"{payload.get('refuting_yield', 0):.2f}")
        macro("retrievalNClaims", str(payload.get("n_claims", "---")))
        macro(
            "retrievalNAnnotated",
            str(payload.get("n_claims_with_annotated_evidence", "---")),
        )
    # Four-way label distribution of V, quoted in the abstention section.
    for family in FAMILY_ORDER:
        tag = "luna" if family == "gpt-6-luna" else "mm"
        for split_name, split_tag in (("dev300", "dev"), ("heldout300", "held")):
            directory = registry["families"][family].get(split_name, {}).get("V")
            if not directory:
                continue
            predictions = ROOT / directory / "predictions.jsonl"
            if not predictions.is_file():
                continue
            counts: dict[str, int] = {}
            for line in predictions.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                label = str(json.loads(line).get("label_4way") or "")
                counts[label] = counts.get(label, 0) + 1
            total = sum(counts.values())
            prefix = f"{tag}{split_tag}Vlabels"
            macro(f"{prefix}total", str(total))
            for label in ("supported", "contradicted", "unaddressed", "underdetermined"):
                macro(f"{prefix}{label}", str(counts.get(label, 0)))
            nei = counts.get("unaddressed", 0) + counts.get("underdetermined", 0)
            macro(f"{prefix}nei", str(nei))
            macro(
                f"{prefix}neishare",
                f"{(nei / total) if total else 0:.2f}",
            )

    # Per-call token averages, quoted in the cost paragraph.
    measured = measured_costs(registry)
    for condition in ("B2", "V"):
        entry = measured.get(("gpt-6-luna", condition))
        if not entry:
            continue
        _, n_calls, total_tokens, _ = entry
        macro(
            f"lunadev{_tex_name(condition)}TokensPerCall",
            f"{(total_tokens / n_calls):,.0f}",
        )

    # Mechanism macros: accuracy conditioned on scope agreement.
    for name, value in (extra or {}).items():
        macro(name, value)

    _write("macros.tex", "\n".join(lines) + "\n")


def write_retrieval_macros() -> None:
    """Deprecated: retrieval macros are written by ``write_macros``."""


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
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}llrrrr@{}}",
        "\\toprule",
        "Method & accounting & $n$ & micro-F1 & FE & SUPPORT R \\\\",
        "\\midrule",
    ]
    first_condition = True
    for family in FAMILY_ORDER:
        blocks = []
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
                    blocks.append(
                        " & ".join(
                            [
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
        if not blocks:
            continue
        if not first_condition:
            lines.append("\\midrule")
        first_condition = False
        lines.append(
            "\\multicolumn{6}{@{}l}{\\emph{"
            + registry_label(family)
            + "}} \\\\[1pt]"
        )
        lines.extend(blocks)
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t1c_sensitivity.tex", "\n".join(lines) + "\n")


def write_mechanism_table(registry: dict, scored: dict) -> dict[str, str]:
    """Accuracy conditioned on whether the two evidence scopes agree.

    This is the mechanism behind the conservative operating point. The V run
    records a rationale code per claim; ``d0_d1_conflict`` means the two
    scopes reached different four-way verdicts and the reconciler abstained.
    The table reports, within each subset, how often the same-evidence baseline
    is right and how often V is right.
    """
    macros: dict[str, str] = {}
    lines = [
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{5pt}",
        "\\begin{tabular}{@{}lrrrr@{}}",
        "\\toprule",
        "Scopes & $n$ & B2 acc. & V acc. & V NEI \\\\",
        "\\midrule",
    ]
    first = True
    for family in FAMILY_ORDER:
        tag = "luna" if family == "gpt-6-luna" else "mm"
        for split_name in ("dev300", "heldout300"):
            conditions = registry["families"][family].get(split_name) or {}
            v_dir = conditions.get("V")
            b2_dir = conditions.get("B2")
            if not v_dir or not b2_dir:
                continue
            v_path = ROOT / v_dir / "predictions.jsonl"
            b2_path = ROOT / b2_dir / "predictions.jsonl"
            if not v_path.is_file() or not b2_path.is_file():
                continue
            report = scored.get(family, {}).get(split_name, {}).get("B2")
            if not report or not report.get("gold_join"):
                continue
            gold = {
                item["claim_id"]: str(item["label_gold"]).upper()
                for item in report["gold_join"]["claims"]
                if item.get("label_gold")
            }
            gold = {
                key: ("REFUTE" if value == "CONTRADICT" else value)
                for key, value in gold.items()
            }

            def read(path: Path) -> dict[str, dict]:
                rows = {}
                for line in path.read_text(encoding="utf-8").splitlines():
                    if not line.strip():
                        continue
                    row = json.loads(line)
                    if row.get("execution_status") not in (None, "ok"):
                        continue
                    rows[row["claim_id"]] = row
                return rows

            v_rows = read(v_path)
            b2_rows = read(b2_path)
            subsets = {"agree": [0, 0, 0, 0], "differ": [0, 0, 0, 0]}
            errors = {"agree": 0, "differ": 0}
            four_way: dict[str, dict[str, int]] = {"agree": {}, "differ": {}}
            for claim_id, gold_label in gold.items():
                v_row = v_rows.get(claim_id)
                b2_row = b2_rows.get(claim_id)
                if not v_row or not b2_row:
                    continue
                codes = v_row.get("rationale_codes") or []
                key = "differ" if "d0_d1_conflict" in codes else "agree"
                counts = subsets[key]
                counts[0] += 1
                counts[1] += int(str(b2_row.get("label")) == gold_label)
                counts[2] += int(str(v_row.get("label")) == gold_label)
                counts[3] += int(str(v_row.get("label")) == "NEI")
                errors[key] += int(str(v_row.get("label")) != gold_label)
                if str(v_row.get("label")) == "NEI":
                    four_way_label = str(v_row.get("label_4way") or "")
                    four_way[key][four_way_label] = (
                        four_way[key].get(four_way_label, 0) + 1
                    )
            if not any(counts[0] for counts in subsets.values()):
                continue
            if not first:
                lines.append("\\midrule")
            first = False
            label = registry_label(family)
            pretty_split = "development" if split_name == "dev300" else "held-out"
            split_tag = "dev" if split_name == "dev300" else "held"
            lines.append(
                "\\multicolumn{5}{@{}l}{\\emph{"
                + label
                + ", "
                + pretty_split
                + "}} \\\\[1pt]"
            )
            for key, name in (("agree", "agree"), ("differ", "differ")):
                n, b2_ok, v_ok, v_nei = subsets[key]
                if n == 0:
                    continue
                lines.append(
                    f"{name} & {n} & {b2_ok / n:.3f} & {v_ok / n:.3f} & "
                    f"{v_nei / n:.3f} \\\\"
                )
                prefix = f"{tag}{split_tag}{'Agree' if key == 'agree' else 'Conflict'}"
                macros[f"{prefix}N"] = str(n)
                macros[f"{prefix}BTwosAcc"] = f"{b2_ok / n:.3f}"
                macros[f"{prefix}Vacc"] = f"{v_ok / n:.3f}"
                macros[f"{prefix}Vnei"] = f"{v_nei / n:.3f}"
                macros[f"{prefix}NeiCount"] = str(v_nei)
            total_errors = errors["agree"] + errors["differ"]
            macros[f"{tag}{split_tag}Verrors"] = str(total_errors)
            macros[f"{tag}{split_tag}VconflictErrors"] = str(errors["differ"])
            for four_way_label, key_name in (
                ("unaddressed", "AgreeUnaddressed"),
                ("underdetermined", "AgreeUnderdetermined"),
            ):
                macros[f"{tag}{split_tag}{key_name}"] = str(
                    four_way["agree"].get(four_way_label, 0)
                )
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    _write("t9_mechanism.tex", "\n".join(lines) + "\n")
    return macros


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
    mechanism_macros = write_mechanism_table(registry, scored)
    write_macros(scored, boots, registry, extra=mechanism_macros)
    print(f"wrote tables under {PAPER_TABLES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
