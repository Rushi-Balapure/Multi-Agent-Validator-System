"""Paper figures, generated from the scored artifacts only.

Every figure is written as a vector PDF into ``paper/figures/`` and mirrored
into ``docs/paper-assets/graphs/`` with a small JSON sidecar that names the
source artifacts. A figure whose source data is missing is not drawn: the
script reports the gap instead of inventing a number.

Run with the paper virtual environment (matplotlib):

    .venv-paper/bin/python scripts/paper/make_figures.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as patches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

from evaluation.score_predictions import score_predictions_file  # noqa: E402

TABLES = ROOT / "docs" / "paper-assets" / "tables"
GRAPHS = ROOT / "docs" / "paper-assets" / "graphs"
FIGURES = ROOT / "paper" / "figures"
REGISTRY = TABLES / "run_registry.json"

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 9,
        "legend.fontsize": 8,
        "axes.grid": True,
        "grid.alpha": 0.25,
        "grid.linestyle": ":",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)

FAMILY_COLORS = {
    "gpt-6-luna": "#1f4e79",
    "minimax-m3.1-flash": "#c0504d",
}
CONDITION_COLORS = {
    "B0": "#a6a6a6",
    "B1": "#4f81bd",
    "B2": "#1f4e79",
    "B3": "#9bbb59",
    "V-D1": "#70ad47",
    "V": "#c0504d",
    "O": "#8064a2",
}


def _registry() -> dict:
    return json.loads(REGISTRY.read_text(encoding="utf-8"))


def _label(registry: dict, family: str) -> str:
    return str(registry["families"][family].get("label", family))


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _native_gold(label: str) -> str:
    token = str(label).strip().upper()
    return "REFUTE" if token == "CONTRADICT" else token


def _gold_map(predictions: Path, sidecar: Path, split: str) -> dict[str, str]:
    report = score_predictions_file(predictions, run_sidecar=sidecar, join_gold=split)
    return {
        item["claim_id"]: _native_gold(item["label_gold"])
        for item in (report.get("gold_join") or {}).get("claims") or []
        if item.get("label_gold")
    }


def _save(fig, name: str, meta: dict) -> None:
    FIGURES.mkdir(parents=True, exist_ok=True)
    GRAPHS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / f"{name}.pdf")
    fig.savefig(GRAPHS / f"{name}.png", dpi=200)
    plt.close(fig)
    (GRAPHS / f"{name}.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(f"  figure {name}")


# --------------------------------------------------------------------------
# architecture
# --------------------------------------------------------------------------
def figure_architecture() -> None:
    fig, ax = plt.subplots(figsize=(7.2, 3.5))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5.2)
    ax.axis("off")

    def box(x, y, w, h, text, style="round,pad=0.02,rounding_size=0.08", fc="#ffffff", ec="#1f4e79"):
        patch = patches.FancyBboxPatch(
            (x, y), w, h, boxstyle=style, linewidth=1.1, edgecolor=ec, facecolor=fc
        )
        ax.add_patch(patch)
        ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=8.5)

    def arrow(x1, y1, x2, y2, style="-|>", color="#1f4e79", ls="-"):
        ax.annotate(
            "",
            xy=(x2, y2),
            xytext=(x1, y1),
            arrowprops={"arrowstyle": style, "color": color, "linestyle": ls, "linewidth": 1.1},
        )

    box(0.15, 3.7, 2.0, 0.85, "Frozen corpus\n(BM25 index)", fc="#eef3f8")
    box(2.55, 3.7, 2.0, 0.85, "Independent\ngatherer", fc="#eef3f8")
    box(4.95, 3.7, 2.0, 0.85, "Sealed reader\n(claim-blind)", fc="#eef3f8")
    box(7.35, 3.7, 2.0, 0.85, "Judge\n(claim-visible)", fc="#fdecea", ec="#c0504d")

    box(2.55, 1.85, 2.0, 0.85, "Citation auditor\n($D_0$ only)", fc="#fdecea", ec="#c0504d")
    box(4.95, 1.85, 2.0, 0.85, "Reconciler\n(scope-separated)", fc="#fff4e5", ec="#e08214")
    box(7.35, 1.85, 2.0, 0.85, "Claim card\n(no new claims)", fc="#f2f2f2", ec="#808080")

    arrow(2.15, 4.12, 2.55, 4.12)
    arrow(4.55, 4.12, 4.95, 4.12)
    arrow(6.95, 4.12, 7.35, 4.12)
    arrow(2.55, 2.27, 4.95, 2.27)
    # Judge output reaches the reconciler along an explicit elbow.
    ax.plot([8.35, 8.35], [3.7, 2.27], color="#e08214", linewidth=1.1)
    arrow(8.35, 2.27, 6.95, 2.27, color="#e08214")
    arrow(6.95, 2.27, 7.35, 2.27)

    ax.text(
        5.0,
        5.02,
        "Claim + neutral question enter only at the judge and the auditor",
        ha="center",
        va="center",
        fontsize=8.5,
        style="italic",
    )
    ax.text(
        5.0,
        1.25,
        "Failure of any stage (transport, parse, out-of-set label) becomes an execution status, never a verdict",
        ha="center",
        va="center",
        fontsize=8,
        style="italic",
        color="#c0504d",
    )
    # The claim reaches the judge only after the reader's record is sealed.
    ax.annotate(
        "",
        xy=(7.45, 3.72),
        xytext=(5.95, 3.35),
        arrowprops={
            "arrowstyle": "-|>",
            "color": "#c0504d",
            "linestyle": "--",
            "linewidth": 1.0,
            "connectionstyle": "arc3,rad=-0.35",
        },
    )
    ax.text(
        6.35,
        2.95,
        "claim revealed\nafter sealing",
        fontsize=7.5,
        color="#c0504d",
        ha="center",
    )
    _save(fig, "architecture", {"figure": "architecture", "source": "method diagram"})


# --------------------------------------------------------------------------
# false endorsement bars
# --------------------------------------------------------------------------
def figure_false_endorsement(registry: dict, scored: dict) -> None:
    conditions = ["B0", "B1", "B2", "B3", "V-D1", "V", "O"]
    families = [f for f in registry["families"] if f in scored]
    fig, ax = plt.subplots(figsize=(7.0, 3.1))
    width = 0.8 / max(len(families), 1)
    positions = list(range(len(conditions)))
    for index, family in enumerate(families):
        values = []
        for condition in conditions:
            report = scored.get(family, {}).get("dev300", {}).get(condition)
            value = None
            if report:
                for item in report.get("metrics") or []:
                    if item.get("metric") == "false_endorsement_gold_nonsup":
                        value = float(item["value"])
                        break
            values.append(value)
        offsets = [p + (index - (len(families) - 1) / 2) * width for p in positions]
        bars = ax.bar(
            offsets,
            [v if v is not None else 0 for v in values],
            width=width * 0.92,
            color=FAMILY_COLORS.get(family, "#444444"),
            label=_label(registry, family),
        )
        for bar, value in zip(bars, values, strict=True):
            if value is None:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                value + 0.008,
                f"{value:.3f}",
                ha="center",
                va="bottom",
                fontsize=7,
                rotation=90,
            )
    ax.set_xticks(positions)
    ax.set_xticklabels(conditions)
    ax.set_ylabel("false endorsement (gold non-support)")
    ax.set_title("False endorsement by condition (development sample)")
    ax.legend(frameon=False)
    _save(
        fig,
        "false_endorsement",
        {
            "figure": "false_endorsement",
            "source": "docs/paper-assets/tables/*_dev300_*_metrics.json",
        },
    )


# --------------------------------------------------------------------------
# four-way label distribution
# --------------------------------------------------------------------------
def figure_label_distribution(registry: dict) -> None:
    entries = []
    for family, family_spec in registry["families"].items():
        directory = family_spec.get("dev300", {}).get("V")
        if not directory:
            continue
        predictions = ROOT / directory / "predictions.jsonl"
        if not predictions.is_file():
            continue
        counts = Counter(
            str(row.get("label_4way") or "") for row in _read_jsonl(predictions)
        )
        entries.append((family, counts))
    if not entries:
        print("  skip label_distribution: no V predictions")
        return
    order = ["supported", "contradicted", "unaddressed", "underdetermined"]
    colors = ["#1f4e79", "#c0504d", "#9bbb59", "#e08214"]
    fig, ax = plt.subplots(figsize=(5.4, 3.0))
    bottoms = [0.0] * len(entries)
    for label, color in zip(order, colors, strict=True):
        values = [counts.get(label, 0) for _, counts in entries]
        ax.barh(
            [f for f, _ in entries],
            values,
            left=bottoms,
            color=color,
            label=label,
        )
        for index, value in enumerate(values):
            if value:
                ax.text(
                    bottoms[index] + value / 2,
                    index,
                    str(value),
                    ha="center",
                    va="center",
                    fontsize=8,
                    color="white",
                )
        bottoms = [b + v for b, v in zip(bottoms, values, strict=True)]
    ax.set_xlabel("claims")
    ax.set_title("Validator V: four-way verdicts before mapping to NEI")
    ax.legend(frameon=False, ncol=2, fontsize=7.5)
    _save(
        fig,
        "label_distribution",
        {
            "figure": "label_distribution",
            "source": "docs/paper-assets/tables/*_dev300_V_metrics.json",
        },
    )


# --------------------------------------------------------------------------
# risk-coverage
# --------------------------------------------------------------------------
def _risk_coverage(scored_items: list[tuple[float, bool]]) -> list[tuple[float, float]]:
    """Coverage and error after accepting the highest-scoring claims first."""
    if not scored_items:
        return []
    ordered = sorted(scored_items, key=lambda item: item[0], reverse=True)
    errors = 0
    points = []
    for rank, (_score, correct) in enumerate(ordered, start=1):
        if not correct:
            errors += 1
        points.append((rank / len(ordered), errors / rank))
    return points


def figure_risk_coverage(registry: dict) -> None:
    curves: list[tuple[str, list[tuple[float, float]], str]] = []
    for family, family_spec in registry["families"].items():
        for condition, directory in family_spec.get("dev300", {}).items():
            predictions = ROOT / directory / "predictions.jsonl"
            sidecar = ROOT / directory / "run.json"
            if not predictions.is_file() or not sidecar.is_file():
                continue
            gold = _gold_map(predictions, sidecar, registry["splits"]["dev300"])
            items: list[tuple[float, bool]] = []
            for row in _read_jsonl(predictions):
                if str(row.get("execution_status") or "ok") != "ok":
                    continue
                label = gold.get(row["claim_id"])
                if not label:
                    continue
                correct = str(row.get("label")) == label
                if condition == "V":
                    score = 1.0 if row.get("d0_label_4way") == row.get("d1_label_4way") else 0.0
                elif condition == "B2":
                    score = 1.0 if row.get("reader_cited_doc_ids") else 0.0
                elif condition in {"B1", "B3"}:
                    value = row.get("confidence")
                    score = float(value) if isinstance(value, (int, float)) else 0.0
                else:
                    continue
                items.append((score, correct))
            points = _risk_coverage(items)
            if points:
                label = f"{condition} ({_label(registry, family).split(' (')[0]})"
                curves.append((label, points, CONDITION_COLORS.get(condition, "#333333")))
    if not curves:
        print("  skip risk_coverage: no scored rows")
        return
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    for label, points, color in curves:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        ax.plot(xs, ys, color=color, linewidth=1.2, label=label, alpha=0.85)
    ax.set_xlabel("coverage (fraction of claims accepted)")
    ax.set_ylabel("error among accepted claims")
    ax.set_title("Selective risk by acceptance rule")
    ax.legend(frameon=False, ncol=2, fontsize=7.5)
    _save(
        fig,
        "risk_coverage",
        {
            "figure": "risk_coverage",
            "source": "docs/paper-assets/tables/*_dev300_*_metrics.json",
            "acceptance_rules": {
                "V": "D0 and D1 four-way verdicts agree",
                "B2": "the sealed reader cited at least one document",
                "B1": "verbalised confidence",
                "B3": "verbalised confidence",
            },
        },
    )


# --------------------------------------------------------------------------
# error composition
# --------------------------------------------------------------------------
def figure_failures() -> None:
    path = TABLES / "failure_taxonomy.json"
    if not path.is_file():
        print("  skip failure_breakdown: run scripts/paper/make_failure_taxonomy.py")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    classes = ["false endorsement", "missed support", "missed contradiction", "other label error"]
    colors = ["#c0504d", "#4f81bd", "#e08214", "#a6a6a6"]
    entries = []
    for family, splits in payload.items():
        for split_name, conditions in splits.items():
            for condition, block in conditions.items():
                if condition not in {"B2", "V"}:
                    continue
                entries.append((f"{condition}\n{family.split('-')[0]}", block))
    if not entries:
        print("  skip failure_breakdown: no entries")
        return
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bottoms = [0.0] * len(entries)
    labels = [entry[0] for entry in entries]
    for name, color in zip(classes, colors, strict=True):
        values = [block["error_classes"].get(name, 0) for _, block in entries]
        ax.bar(labels, values, bottom=bottoms, color=color, label=name)
        bottoms = [b + v for b, v in zip(bottoms, values, strict=True)]
    ax.set_ylabel("scored errors")
    ax.set_title("Error composition of the same-evidence baseline and the staged validator")
    ax.legend(frameon=False, ncol=2, fontsize=7.5)
    _save(
        fig,
        "failure_breakdown",
        {"figure": "failure_breakdown", "source": "docs/paper-assets/tables/failure_taxonomy.json"},
    )


# --------------------------------------------------------------------------
# accuracy against cost
# --------------------------------------------------------------------------
def figure_accuracy_cost(registry: dict, scored: dict) -> None:
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    for family, family_spec in registry["families"].items():
        points = []
        for condition, directory in family_spec.get("dev300", {}).items():
            sidecar_path = ROOT / directory / "run.json"
            report = scored.get(family, {}).get("dev300", {}).get(condition)
            if not sidecar_path.is_file() or not report:
                continue
            sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
            usage = (sidecar.get("run") or {}).get("tokens") or {}
            n = sidecar.get("n_predictions") or 1
            tokens = (usage.get("total_tokens") or 0) / max(int(n), 1)
            micro = None
            for item in report.get("metrics") or []:
                if item.get("metric") == "micro_f1":
                    micro = float(item["value"])
            if micro is None or tokens <= 0:
                continue
            points.append((tokens, micro, condition))
        if not points:
            continue
        ax.scatter(
            [p[0] for p in points],
            [p[1] for p in points],
            s=42,
            color=FAMILY_COLORS.get(family, "#333333"),
            label=_label(registry, family),
            zorder=3,
        )
        for tokens, micro, condition in points:
            ax.annotate(
                condition,
                (tokens, micro),
                textcoords="offset points",
                xytext=(5, 4),
                fontsize=7.5,
            )
    ax.set_xscale("log")
    ax.set_xlabel("tokens per claim (log scale)")
    ax.set_ylabel("micro-F1")
    ax.set_title("Verification quality against cost")
    ax.legend(frameon=False, fontsize=7.5)
    _save(
        fig,
        "accuracy_cost",
        {
            "figure": "accuracy_cost",
            "source": "docs/paper-assets/tables/*_dev300_*_metrics.json and run sidecars",
        },
    )


# --------------------------------------------------------------------------
# reliability
# --------------------------------------------------------------------------
def figure_reliability() -> None:
    path = TABLES / "calibration_by_family.json"
    if not path.is_file():
        print("  skip reliability: run scripts/paper/make_calibration.py")
        return
    payload = json.loads(path.read_text(encoding="utf-8"))
    fig, ax = plt.subplots(figsize=(4.6, 4.2))
    ax.plot([0, 1], [0, 1], color="#999999", linestyle="--", linewidth=1.0, label="perfect calibration")
    drawn = False
    for family, block in payload.items():
        entry = block.get("dev300") or block.get("calibration")
        if not entry:
            continue
        points = entry.get("reliability") or []
        xs = [p["confidence"] for p in points if p["n"] >= 3]
        ys = [p["accuracy"] for p in points if p["n"] >= 3]
        if not xs:
            continue
        ax.plot(
            xs,
            ys,
            marker="o",
            markersize=4,
            color=FAMILY_COLORS.get(family, "#333333"),
            label=family,
        )
        drawn = True
    if not drawn:
        print("  skip reliability: no reliability bins")
        plt.close(fig)
        return
    ax.set_xlabel("predicted probability")
    ax.set_ylabel("observed accuracy")
    ax.set_title("Reliability of the claim-visible judge (B1)")
    ax.legend(frameon=False, fontsize=7.5)
    _save(
        fig,
        "reliability",
        {"figure": "reliability", "source": "docs/paper-assets/tables/calibration_by_family.json"},
    )


def main() -> int:
    registry = _registry()
    scored: dict = {}
    for family, family_spec in registry["families"].items():
        scored[family] = {}
        for split_name, conditions in family_spec.items():
            if split_name == "label":
                continue
            split = registry["splits"][split_name]
            scored[family][split_name] = {}
            for condition, directory in conditions.items():
                predictions = ROOT / directory / "predictions.jsonl"
                sidecar = ROOT / directory / "run.json"
                if not predictions.is_file() or not sidecar.is_file():
                    continue
                scored[family][split_name][condition] = score_predictions_file(
                    predictions, run_sidecar=sidecar, join_gold=split
                )
    print("writing figures")
    figure_architecture()
    figure_false_endorsement(registry, scored)
    figure_label_distribution(registry)
    figure_risk_coverage(registry)
    figure_failures()
    figure_accuracy_cost(registry, scored)
    figure_reliability()
    print(f"wrote figures under {FIGURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
