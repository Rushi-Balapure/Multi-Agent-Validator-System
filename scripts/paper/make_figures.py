"""Paper figures, generated from the scored artifacts only.

Every figure is written as a vector PDF into ``paper/figures/`` and mirrored
into ``docs/paper-assets/graphs/`` with a small JSON sidecar that names the
source artifacts. A figure whose source data is missing is not drawn: the
script reports the gap instead of inventing a number.

Run with the paper virtual environment (matplotlib):

    .venv-paper/bin/python scripts/paper/make_figures.py
"""

from __future__ import annotations

import datetime as dt
import json
import os
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
import matplotlib.ticker as mticker  # noqa: E402

from evaluation.score_predictions import score_predictions_file  # noqa: E402

TABLES = ROOT / "docs" / "paper-assets" / "tables"
GRAPHS = ROOT / "docs" / "paper-assets" / "graphs"
FIGURES = ROOT / "paper" / "figures"
REGISTRY = TABLES / "run_registry.json"

# Pin the PDF creation date so that regenerating a figure from unchanged data
# produces an identical file. Without this, matplotlib stamps the wall clock
# into the document info and every rebuild shows a binary diff. Set
# SOURCE_DATE_EPOCH to override the pinned date.
_EPOCH = int(os.environ.get("SOURCE_DATE_EPOCH", "1790812800"))  # 2026-10-01 UTC
_PDF_DATE = dt.datetime.fromtimestamp(_EPOCH, dt.timezone.utc)
_PDF_META = {"CreationDate": _PDF_DATE, "ModDate": _PDF_DATE}

plt.rcParams.update(
    {
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
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


ACCESS_COLORS = {"closed": "#1f4e79", "open": "#c0504d"}


def _sweep_items(registry: dict) -> list[tuple[str, dict, dict]]:
    """Sweep rows in registry order, skipping models that have not run."""
    items: list[tuple[str, dict, dict]] = []
    models = (registry.get("sweep") or {}).get("models") or {}
    for key, spec in models.items():
        path = TABLES / f"sweep_{key}.json"
        if not path.is_file():
            continue
        items.append((key, spec, json.loads(path.read_text(encoding="utf-8"))))
    return items


def _report_metric(report: dict, name: str) -> float | None:
    for item in report.get("metrics") or []:
        if item.get("metric") == name:
            return float(item["value"])
    return None


def _report_class_metric(report: dict, name: str, label: str) -> float | None:
    for item in report.get("metrics") or []:
        if item.get("metric") == name and item.get("class") == label:
            return float(item["value"])
    return None


def _sweep_delta(item: dict) -> dict | None:
    bootstrap = (item.get("comparison") or {}).get("bootstrap") or {}
    return (bootstrap.get("paired_difference") or {}).get("false_endorsement_gold_nonsup")


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
    fig.savefig(FIGURES / f"{name}.pdf", metadata=_PDF_META)
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
    # Judge output reaches the reconciler through the gap between the
    # reconciler and the claim card, so no edge crosses a box.
    ax.plot([7.35, 7.15], [3.78, 3.78], color="#e08214", linewidth=1.1)
    ax.plot([7.15, 7.15], [3.78, 2.27], color="#e08214", linewidth=1.1)
    arrow(7.15, 2.27, 6.95, 2.27, color="#e08214")
    arrow(6.95, 2.10, 7.35, 2.10)

    ax.text(
        3.9,
        5.02,
        "Each role sees only what its contract allows",
        ha="center",
        va="center",
        fontsize=8.5,
        style="italic",
    )
    # The claim reaches the judge only after the reader's record is sealed;
    # the dashed arrow is that single path.
    ax.annotate(
        "",
        xy=(8.55, 4.56),
        xytext=(8.55, 4.99),
        arrowprops={
            "arrowstyle": "-|>",
            "color": "#c0504d",
            "linestyle": "--",
            "linewidth": 1.0,
        },
    )
    ax.text(
        8.38,
        4.86,
        "claim, revealed\nafter sealing",
        fontsize=7,
        color="#c0504d",
        ha="right",
        va="center",
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
    _save(fig, "architecture", {"figure": "architecture", "source": "method diagram"})


def _flow_box(ax, x: float, y: float, label: str, color: str) -> None:
    patch = patches.FancyBboxPatch(
        (x, y), 1.75, 0.78, boxstyle="round,pad=0.03",
        linewidth=1, edgecolor="#334155", facecolor=color,
    )
    ax.add_patch(patch)
    ax.text(x + 0.875, y + 0.39, label, ha="center", va="center", fontsize=7.4)


def _flow_arrow(ax, points, *, dashed: bool = False) -> None:
    """Polyline arrow through ``points`` with a head on the last segment."""
    style = {"color": "#475569", "lw": 1.1, "linestyle": "--" if dashed else "-"}
    for (x1, y1), (x2, y2) in zip(points[:-2], points[1:-1]):
        ax.plot([x1, x2], [y1, y2], **style)
    (x1, y1), (x2, y2) = points[-2], points[-1]
    ax.annotate(
        "",
        (x2, y2),
        (x1, y1),
        arrowprops={"arrowstyle": "-|>", **style},
    )


def figure_data_flow() -> None:
    """The records passed between stages, for one claim.

    Two paths run in parallel: the sealed D1 path (neutral question through
    independent retrieval) and the D0 path (the claim beside its own
    citations). They meet only in the reconciler, which is the point of the
    design. The D0 arrow is routed under the D1 row so that no edge crosses a
    box.
    """
    fig, ax = plt.subplots(figsize=(7.4, 3.0))
    ax.set(xlim=(0, 10.15), ylim=(0, 3.55))
    ax.axis("off")

    top, bottom, middle = 2.42, 1.02, 1.68
    boxes = [
        (0.10, middle, "Claim", "#fff0e9"),
        (2.10, top, "Neutral\nquestion", "#e8f1fa"),
        (2.10, bottom, "Claim + original\ncitations", "#fff0e9"),
        (4.15, top, "BM25\nretrieval", "#e8f1fa"),
        (4.15, bottom, "D0 citation\nauditor", "#fff0e9"),
        (6.20, top, "Sealed reader\nrecord", "#e8f1fa"),
        (6.20, bottom, "D1 claim\njudge", "#fff0e9"),
        (8.25, middle, "Reconciled\nclaim card", "#f3ebfa"),
    ]
    for x, y, label, color in boxes:
        _flow_box(ax, x, y, label, color)

    _flow_arrow(ax, [(1.85, middle + 0.45), (1.98, top), (2.10, top + 0.20)])
    _flow_arrow(ax, [(1.85, middle + 0.33), (1.98, bottom + 0.78), (2.10, bottom + 0.58)])
    _flow_arrow(ax, [(3.85, top + 0.39), (4.15, top + 0.39)])
    _flow_arrow(ax, [(3.85, bottom + 0.39), (4.15, bottom + 0.39)])
    _flow_arrow(ax, [(5.90, top + 0.39), (6.20, top + 0.39)])
    _flow_arrow(
        ax,
        [(7.075, top), (7.075, bottom + 0.78)],
        dashed=True,
    )
    # D0 reaches the reconciler from below, routed under the D1 row so no
    # edge crosses a box.
    _flow_arrow(
        ax,
        [(5.60, bottom), (5.60, 0.68), (9.45, 0.68), (9.45, middle)],
    )
    _flow_arrow(ax, [(7.95, bottom + 0.72), (8.25, middle + 0.20)])
    ax.text(
        7.16,
        (top + bottom) / 2 + 0.39,
        "claim revealed\nafter sealing",
        ha="left",
        va="center",
        fontsize=6.6,
        color="#475569",
        bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.6},
    )
    ax.text(
        5.07,
        0.20,
        "Execution failure \u2192 status record (no scientific verdict)",
        ha="center",
        fontsize=8,
        color="#9b2c2c",
    )
    _save(fig, "data_flow", {"figure": "data_flow", "source": "method diagram"})


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
        labelled = False
        for offset, value in zip(offsets, values, strict=True):
            if value is None:
                ax.text(offset, 0.008, "n/a", ha="center", fontsize=6, rotation=90)
                continue
            bars = ax.bar(
                offset, value, width=width * 0.92,
                color=FAMILY_COLORS.get(family, "#444444"),
                label=_label(registry, family) if not labelled else None,
            )
            labelled = True
            bar = bars[0]
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
    display = {
        "gpt-6-luna": "GPT-6 Luna",
        "minimax-m3.1-flash": "MiniMax M3.1 Flash",
    }
    fig, ax = plt.subplots(figsize=(5.4, 3.2))
    bottoms = [0.0] * len(entries)
    for label, color in zip(order, colors, strict=True):
        values = [counts.get(label, 0) for _, counts in entries]
        ax.barh(
            [display.get(family, family) for family, _ in entries],
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
    ax.set_xlim(0, max(bottoms) * 1.02)
    ax.set_title("Validator V: four-way verdicts before mapping to NEI")
    ax.legend(
        frameon=False,
        ncol=4,
        fontsize=7.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
    )
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
                short = "Luna" if family == "gpt-6-luna" else "MiniMax"
                label = f"{condition} ({short})"
                curves.append((label, points, CONDITION_COLORS.get(condition, "#333333")))
    if not curves:
        print("  skip risk_coverage: no scored rows")
        return
    fig, ax = plt.subplots(figsize=(6.4, 3.6))
    for label, points, color in curves:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        ax.plot(xs, ys, color=color, linewidth=1.2, label=label, alpha=0.85)
    ax.set_xlabel("coverage (fraction of claims accepted)")
    ax.set_ylabel("error among accepted claims")
    ax.set_title("Selective risk by acceptance rule")
    ax.legend(
        frameon=False,
        ncol=3,
        fontsize=7.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
    )
    fig.tight_layout()
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
    short = {"gpt-6-luna": "Luna", "minimax-m3.1-flash": "MiniMax"}
    entries = []
    for family, splits in payload.items():
        conditions = splits.get("dev300") or {}
        for condition in ("B2", "V"):
            block = conditions.get(condition)
            if not block:
                continue
            entries.append((f"{condition}\n{short.get(family, family)}", block))
    if not entries:
        print("  skip failure_breakdown: no entries")
        return
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    bottoms = [0.0] * len(entries)
    labels = [entry[0] for entry in entries]
    for name, color in zip(classes, colors, strict=True):
        values = [block["error_classes"].get(name, 0) for _, block in entries]
        ax.bar(labels, values, bottom=bottoms, color=color, label=name)
        bottoms = [b + v for b, v in zip(bottoms, values, strict=True)]
    ax.set_ylabel("scored errors")
    ax.set_title("Error composition of the baseline and the staged validator")
    ax.legend(
        frameon=False,
        ncol=4,
        fontsize=7.5,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.18),
    )
    _save(
        fig,
        "failure_breakdown",
        {"figure": "failure_breakdown", "source": "docs/paper-assets/tables/failure_taxonomy.json"},
    )


# --------------------------------------------------------------------------
# accuracy against cost
# --------------------------------------------------------------------------
def figure_accuracy_cost(registry: dict, scored: dict) -> None:
    """Micro-F1 against the prompt size of one call.

    Per-call size is used rather than per-claim totals because resumed runs
    keep only the usage meter of their last invocation. Where the development
    sidecar is too small to measure (V in the API family), the held-out run
    supplies the per-call figure.
    """
    fig, ax = plt.subplots(figsize=(5.8, 3.3))
    for family, family_spec in registry["families"].items():
        points = []
        tag = "luna" if family == "gpt-6-luna" else "minimax"
        for condition, directory in family_spec.get("dev300", {}).items():
            candidates = [ROOT / directory / "run.json"]
            if family == "gpt-6-luna":
                held = family_spec.get("heldout300", {}).get(condition)
                if held:
                    candidates.append(ROOT / held / "run.json")
            candidates.append(ROOT / "artifacts" / "cost_probe" / tag / condition / "run.json")
            n_calls = 0
            tokens_per_call = 0.0
            for candidate in candidates:
                if not candidate.is_file():
                    continue
                usage = (
                    json.loads(candidate.read_text(encoding="utf-8")).get("run") or {}
                ).get("tokens") or {}
                calls = int(usage.get("n_calls") or 0)
                if calls >= 100:
                    n_calls = calls
                    tokens_per_call = (usage.get("total_tokens") or 0) / calls
                    break
                if calls > n_calls:
                    n_calls = calls
                    tokens_per_call = (usage.get("total_tokens") or 0) / calls
            report = scored.get(family, {}).get("dev300", {}).get(condition)
            if not report or n_calls <= 0:
                continue
            micro = None
            for item in report.get("metrics") or []:
                if item.get("metric") == "micro_f1":
                    micro = float(item["value"])
            if micro is None:
                continue
            points.append((tokens_per_call, micro, condition))
        if not points:
            continue
        ax.scatter(
            [p[0] for p in points],
            [p[1] for p in points],
            s=44,
            color=FAMILY_COLORS.get(family, "#333333"),
            label=_label(registry, family),
            zorder=3,
        )
        largest = max(p[0] for p in points)
        for tokens, micro, condition in points:
            # Keep labels inside the axes at both ends of the log scale.
            if tokens >= largest:
                kwargs = {"xytext": (-6, 4), "ha": "right"}
            elif tokens <= min(p[0] for p in points):
                kwargs = {"xytext": (7, -2), "ha": "left"}
            else:
                kwargs = {"xytext": (6, 4), "ha": "left"}
            ax.annotate(
                condition,
                (tokens, micro),
                textcoords="offset points",
                fontsize=7.5,
                **kwargs,
            )
    ax.set_xscale("log")
    ax.xaxis.set_minor_formatter(mticker.NullFormatter())
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_xticks([300, 600, 1200, 3000])
    ax.set_xlabel("prompt tokens per call (log scale)")
    ax.set_ylabel("micro-F1")
    ax.set_title("Verification quality against per-call prompt size")
    ax.legend(frameon=False, fontsize=7.5, loc="best")
    fig.tight_layout()
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
def figure_reliability(registry: dict) -> None:
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
            label=_label(registry, family),
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


def figure_model_sweep(registry: dict) -> None:
    """B2 to V per model on the four outcomes the sweep can speak to.

    A dumbbell rather than a forest: on a thirty-claim subset the paired
    false-endorsement interval collapses to a point at zero, which hides the
    shift that actually happens. The shift is visible as lost REFUTE recall
    while SUPPORT recall and false endorsement stay put.
    """
    items = _sweep_items(registry)
    if len(items) < 3:
        print("  skip model_sweep: fewer than three sweep models scored")
        return

    panels = [
        ("micro_f1", None, "micro-F1"),
        ("false_endorsement_gold_nonsup", None, "false endorsement"),
        ("recall", "SUPPORT", "SUPPORT recall"),
        ("recall", "REFUTE", "REFUTE recall"),
    ]
    fig, axes = plt.subplots(1, len(panels), figsize=(7.2, 1.3 + 0.24 * len(items)), sharey=True)
    positions = list(range(len(items)))[::-1]
    for ax, (metric, class_label, title) in zip(axes, panels):
        for y, (key, spec, data) in zip(positions, items):
            access = spec.get("access", "")
            color = ACCESS_COLORS.get(access, "#444444")

            def value(report: dict) -> float | None:
                if class_label is None:
                    return _report_metric(report, metric)
                return _report_class_metric(report, metric, class_label)

            b2_value = value(data["b2"])
            v_value = value(data["v"])
            if b2_value is None or v_value is None:
                continue
            ax.plot([b2_value * 100, v_value * 100], [y, y],
                    color=color, linewidth=1.0, alpha=0.55)
            ax.scatter(b2_value * 100, y, s=20, facecolors="none",
                       edgecolors=color, linewidths=1.0, zorder=3)
            ax.scatter(v_value * 100, y, s=22, color=color, zorder=4)
        ax.set_title(title, fontsize=8)
        ax.set_xlim(-4, 104)
        ax.set_xlabel("%", fontsize=7)
        ax.tick_params(axis="x", labelsize=7)
        ax.grid(axis="x", linestyle=":", linewidth=0.5, alpha=0.6)
    axes[0].set_yticks(positions)
    axes[0].set_yticklabels([spec["label"] for _key, spec, _data in items], fontsize=6.6)
    axes[0].set_ylim(-0.7, len(items) - 0.3)
    axes[0].scatter([], [], s=20, facecolors="none", edgecolors="#555555", label="B2")
    axes[0].scatter([], [], s=22, color="#555555", label="V")
    axes[0].legend(frameon=False, fontsize=6.4, loc="lower left")
    fig.tight_layout(pad=0.4)
    _save(
        fig,
        "model_sweep",
        {"figure": "model_sweep", "source": "docs/paper-assets/tables/sweep_*.json"},
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
    figure_data_flow()
    figure_false_endorsement(registry, scored)
    figure_label_distribution(registry)
    figure_risk_coverage(registry)
    figure_failures()
    figure_accuracy_cost(registry, scored)
    figure_reliability(registry)
    figure_model_sweep(registry)
    print(f"wrote figures under {FIGURES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
