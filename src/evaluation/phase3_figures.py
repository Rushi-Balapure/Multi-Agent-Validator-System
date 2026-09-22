"""Phase-3 figure drafts from checked-in prediction / metrics artifacts only.

Reads saved files under ``docs/paper-assets/tables/`` and writes SVG + PNG
drafts plus ``.meta.json`` citing run_ids. Does not invent metric values:
cited-D0 V FE rates come from scored metrics; fail-closed history figures
cite the #23 gather set without overwriting those tables.

    PYTHONPATH=src python -m evaluation.phase3_figures
"""

from __future__ import annotations

import argparse
import json
import struct
import zlib
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "docs" / "paper-assets" / "graphs"
V_PRED = (
    ROOT
    / "docs"
    / "paper-assets"
    / "tables"
    / "validator_v_gather_cited_d0"
    / "predictions.jsonl"
)
V_SIDE = (
    ROOT / "docs" / "paper-assets" / "tables" / "validator_v_gather_cited_d0" / "run.json"
)
V_METRICS = (
    ROOT
    / "docs"
    / "paper-assets"
    / "tables"
    / "validator_v_gather_cited_d0"
    / "v_gather_cited_d0_metrics.json"
)
# Fail-closed #23 comparison history (not overwritten).
FAIL_CLOSED_PRED = (
    ROOT / "docs" / "paper-assets" / "tables" / "validator_v_gather" / "predictions.jsonl"
)
FAIL_CLOSED_SIDE = (
    ROOT / "docs" / "paper-assets" / "tables" / "validator_v_gather" / "run.json"
)
FAIL_CLOSED_METRICS = (
    ROOT / "docs" / "paper-assets" / "tables" / "validator_v_gather" / "v_gather_metrics.json"
)
B2_METRICS = ROOT / "docs" / "paper-assets" / "tables" / "b2_live_n20_metrics.json"
CITED_D0_RUN = "validator-v-gather-development-s0-n20-3c856362819b"
FAIL_CLOSED_RUN = "validator-v-gather-development-s0-n20-90129d9056fd"
B2_RUN = "same-evidence-b2-development-s0-n20-dac855c4e2ae"


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _png_rgba(width: int, height: int, rgba: Sequence[tuple[int, int, int, int]]) -> bytes:
    """Minimal PNG encoder (RGBA). ``rgba`` is row-major length width*height."""
    if len(rgba) != width * height:
        raise ValueError("rgba length must equal width*height")
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter none
        for x in range(width):
            r, g, b, a = rgba[y * width + x]
            raw.extend((r, g, b, a))
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", ihdr),
            chunk(b"IDAT", compressed),
            chunk(b"IEND", b""),
        )
    )


def _fill(
    buf: list[tuple[int, int, int, int]],
    width: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int, int],
) -> None:
    height = len(buf) // width
    for y in range(max(0, y0), min(height, y1)):
        for x in range(max(0, x0), min(width, x1)):
            buf[y * width + x] = color


def _write_bar_chart_png(
    path: Path,
    *,
    title: str,
    labels: Sequence[str],
    values: Sequence[float | None],
    value_labels: Sequence[str],
    width: int = 720,
    height: int = 420,
) -> None:
    bg = (250, 248, 244, 255)
    axis = (40, 40, 40, 255)
    bar_b2 = (46, 92, 138, 255)
    bar_skip = (160, 160, 160, 255)
    buf = [bg] * (width * height)
    margin_l, margin_r, margin_t, margin_b = 70, 30, 50, 70
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    _fill(buf, width, margin_l, margin_t, margin_l + 2, margin_t + plot_h, axis)
    _fill(
        buf,
        width,
        margin_l,
        margin_t + plot_h,
        margin_l + plot_w,
        margin_t + plot_h + 2,
        axis,
    )
    n = len(labels)
    slot = plot_w / max(n, 1)
    bar_w = int(slot * 0.55)
    numeric = [v for v in values if v is not None]
    ymax = max(numeric) if numeric else 1.0
    if ymax <= 0:
        ymax = 1.0
    for i, (label, value) in enumerate(zip(labels, values)):
        x = int(margin_l + slot * i + (slot - bar_w) / 2)
        if value is None:
            y0 = margin_t + plot_h - 24
            _fill(buf, width, x, y0, x + bar_w, margin_t + plot_h, bar_skip)
        else:
            h = int((value / ymax) * (plot_h - 10))
            y0 = margin_t + plot_h - h
            color = bar_b2 if i == 0 else (70, 130, 90, 255)
            _fill(buf, width, x, y0, x + bar_w, margin_t + plot_h, color)
    path.write_bytes(_png_rgba(width, height, buf))
    # Title/labels live in the SVG companion; PNG is the geometric bars only.
    _ = (title, value_labels)


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _svg_bars(
    *,
    title: str,
    subtitle: str,
    categories: Sequence[tuple[str, float | None, str]],
    y_caption: str,
) -> str:
    width, height = 720, 420
    margin_l, margin_r, margin_t, margin_b = 80, 40, 70, 90
    plot_w = width - margin_l - margin_r
    plot_h = height - margin_t - margin_b
    numeric = [v for _, v, _ in categories if v is not None]
    ymax = max(numeric) if numeric else 1.0
    if ymax <= 0:
        ymax = 1.0
    n = len(categories)
    slot = plot_w / max(n, 1)
    bar_w = slot * 0.55
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#faf8f4"/>',
        f'<text x="{width/2}" y="28" text-anchor="middle" '
        f'font-family="Georgia, serif" font-size="18">{_escape(title)}</text>',
        f'<text x="{width/2}" y="50" text-anchor="middle" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="11" fill="#444">'
        f"{_escape(subtitle)}</text>",
        f'<line x1="{margin_l}" y1="{margin_t}" x2="{margin_l}" '
        f'y2="{margin_t + plot_h}" stroke="#282828" stroke-width="1.5"/>',
        f'<line x1="{margin_l}" y1="{margin_t + plot_h}" x2="{margin_l + plot_w}" '
        f'y2="{margin_t + plot_h}" stroke="#282828" stroke-width="1.5"/>',
        f'<text x="18" y="{margin_t + plot_h/2}" transform='
        f'"rotate(-90 18 {margin_t + plot_h/2})" '
        f'font-family="Helvetica, Arial, sans-serif" font-size="11">'
        f"{_escape(y_caption)}</text>",
    ]
    colors = ["#2e5c8a", "#46825a", "#8a5a2e", "#5a6a8a"]
    for i, (label, value, display) in enumerate(categories):
        x = margin_l + slot * i + (slot - bar_w) / 2
        if value is None:
            h = 28
            y = margin_t + plot_h - h
            fill = "#a0a0a0"
        else:
            h = max(2.0, (value / ymax) * (plot_h - 10))
            y = margin_t + plot_h - h
            fill = colors[i % len(colors)]
        parts.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{h:.1f}" '
            f'fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{x + bar_w/2:.1f}" y="{y - 8:.1f}" text-anchor="middle" '
            f'font-family="Helvetica, Arial, sans-serif" font-size="12">'
            f"{_escape(display)}</text>"
        )
        parts.append(
            f'<text x="{x + bar_w/2:.1f}" y="{margin_t + plot_h + 22:.1f}" '
            f'text-anchor="middle" font-family="Helvetica, Arial, sans-serif" '
            f'font-size="11">{_escape(label)}</text>'
        )
    parts.append("</svg>")
    return "\n".join(parts)


def _write_meta(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _fe_metric(report: Mapping[str, Any], name: str) -> float:
    for row in report.get("metrics", []):
        if (
            isinstance(row, Mapping)
            and row.get("formula_id") == "F-false-endorsement"
            and row.get("metric") == name
        ):
            value = row.get("value")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    raise KeyError(name)


def build_fe_compare(
    *,
    b2_report: Mapping[str, Any],
    v_report: Mapping[str, Any],
    out_dir: Path,
) -> None:
    b2_run = str(b2_report["run_id"])
    v_run = str(v_report["run_id"])
    gold = _fe_metric(b2_report, "false_endorsement_gold_nonsup")
    pred = _fe_metric(b2_report, "false_endorsement_pred_sup")
    v_skipped = v_report.get("scoring_status") == "skipped_not_ok"
    if v_skipped:
        v_gold: float | None = None
        v_pred: float | None = None
        v_gold_disp = "N/A"
        v_pred_disp = "N/A"
        v_fe_rates = None
        y_caption = "rate (V FE = N/A)"
        note = (
            "V FE rates are N/A because every gather row is execution_status "
            "not ok (fail-closed D0). Values are taken only from saved metrics."
        )
    else:
        v_gold = _fe_metric(v_report, "false_endorsement_gold_nonsup")
        v_pred = _fe_metric(v_report, "false_endorsement_pred_sup")
        v_gold_disp = f"{v_gold:.4f}"
        v_pred_disp = f"{v_pred:.4f}"
        v_fe_rates = {
            "false_endorsement_gold_nonsup": v_gold,
            "false_endorsement_pred_sup": v_pred,
        }
        y_caption = "F-false-endorsement rate"
        note = (
            "V FE rates from scored cited-D0 metrics "
            f"(n_scored={v_report.get('n_scored')}, "
            f"n_skipped_not_ok={v_report.get('n_skipped_not_ok')}). "
            "Values are taken only from saved metrics."
        )
    categories = [
        ("B2 FE gold-nonsup", gold, f"{gold:.4f}"),
        ("B2 FE pred-sup", pred, f"{pred:.4f}"),
        ("V FE gold-nonsup", v_gold, v_gold_disp),
        ("V FE pred-sup", v_pred, v_pred_disp),
    ]
    stem = out_dir / "fe_bar_v_vs_b2"
    svg = _svg_bars(
        title="F-false-endorsement: V cited-D0 vs B2 live",
        subtitle=f"B2 `{b2_run}` · V `{v_run}`",
        categories=categories,
        y_caption=y_caption,
    )
    stem.with_suffix(".svg").write_text(svg + "\n", encoding="utf-8")
    _write_bar_chart_png(
        stem.with_suffix(".png"),
        title="F-false-endorsement: V cited-D0 vs B2 live",
        labels=[c[0] for c in categories],
        values=[c[1] for c in categories],
        value_labels=[c[2] for c in categories],
    )
    _write_meta(
        Path(str(stem) + ".meta.json"),
        {
            "figure_id": "fe_bar_v_vs_b2",
            "formula_id": "F-false-endorsement",
            "b2_run_id": b2_run,
            "v_run_id": v_run,
            "sources": {
                "b2_metrics": str(B2_METRICS.relative_to(ROOT)),
                "v_metrics": str(V_METRICS.relative_to(ROOT)),
                "v_predictions": str(V_PRED.relative_to(ROOT)),
            },
            "b2_false_endorsement_gold_nonsup": gold,
            "b2_false_endorsement_pred_sup": pred,
            "v_scoring_status": v_report.get("scoring_status"),
            "v_n_skipped_not_ok": v_report.get("n_skipped_not_ok"),
            "v_n_scored": v_report.get("n_scored"),
            "v_fe_rates": v_fe_rates,
            "note": note,
        },
    )


def build_v_histograms(
    *,
    rows: Sequence[Mapping[str, Any]],
    v_report: Mapping[str, Any],
    sidecar: Mapping[str, Any],
    out_dir: Path,
) -> None:
    run = sidecar.get("run", {})
    run_id = run.get("run_id") if isinstance(run, Mapping) else None
    if not isinstance(run_id, str):
        run_id = str(v_report["run_id"])
    labels = Counter(str(r.get("label")) for r in rows)
    status = Counter(str(r.get("execution_status")) for r in rows)
    four = Counter(str(r.get("label_4way")) for r in rows)
    d1 = Counter(str(r.get("d1_label_4way")) for r in rows)

    cats = [(lab, float(count), str(count)) for lab, count in sorted(labels.items())]
    stem = out_dir / "v_gather_label_histogram"
    svg = _svg_bars(
        title="V cited-D0 gather predicted label histogram",
        subtitle=f"run `{run_id}` · n={len(rows)} rows from saved predictions.jsonl",
        categories=cats,
        y_caption="count",
    )
    stem.with_suffix(".svg").write_text(svg + "\n", encoding="utf-8")
    _write_bar_chart_png(
        stem.with_suffix(".png"),
        title="V cited-D0 gather predicted label histogram",
        labels=[c[0] for c in cats],
        values=[c[1] for c in cats],
        value_labels=[c[2] for c in cats],
    )
    _write_meta(
        Path(str(stem) + ".meta.json"),
        {
            "figure_id": "v_gather_label_histogram",
            "v_run_id": run_id,
            "b2_run_id": B2_RUN,
            "source_predictions": str(V_PRED.relative_to(ROOT)),
            "counts_by_label": dict(labels),
            "counts_by_label_4way": dict(four),
            "n_rows": len(rows),
            "note": (
                "Histogram of artifact `label` fields only from cited-D0 gather. "
                f"n_skipped_not_ok={v_report.get('n_skipped_not_ok')}; "
                f"n_scored={v_report.get('n_scored')}."
            ),
        },
    )

    cats2 = [(lab, float(count), str(count)) for lab, count in sorted(status.items())]
    stem2 = out_dir / "v_gather_cited_d0_status"
    svg2 = _svg_bars(
        title="V cited-D0 gather execution_status",
        subtitle=(
            f"run `{run_id}` · n_skipped_not_ok="
            f'{v_report.get("n_skipped_not_ok")}/{v_report.get("n_rows")} · '
            f'n_scored={v_report.get("n_scored")}'
        ),
        categories=cats2,
        y_caption="count",
    )
    stem2.with_suffix(".svg").write_text(svg2 + "\n", encoding="utf-8")
    _write_bar_chart_png(
        stem2.with_suffix(".png"),
        title="V cited-D0 gather execution_status",
        labels=[c[0] for c in cats2],
        values=[c[1] for c in cats2],
        value_labels=[c[2] for c in cats2],
    )
    _write_meta(
        Path(str(stem2) + ".meta.json"),
        {
            "figure_id": "v_gather_cited_d0_status",
            "v_run_id": run_id,
            "b2_run_id": B2_RUN,
            "source_predictions": str(V_PRED.relative_to(ROOT)),
            "source_metrics": str(V_METRICS.relative_to(ROOT)),
            "counts_by_execution_status": dict(status),
            "counts_by_d1_label_4way": dict(d1),
            "n_skipped_not_ok": v_report.get("n_skipped_not_ok"),
            "n_scored": v_report.get("n_scored"),
            "scoring_status": v_report.get("scoring_status"),
            "note": (
                "Cited-D0 gather execution_status from saved predictions. "
                "Failed rows are skipped by F-false-endorsement; not remapped."
            ),
        },
    )


def build_fail_closed_history(
    *,
    rows: Sequence[Mapping[str, Any]],
    v_report: Mapping[str, Any],
    sidecar: Mapping[str, Any],
    out_dir: Path,
) -> None:
    """Keep the #23 fail-closed status figure as comparison history."""
    run = sidecar.get("run", {})
    run_id = run.get("run_id") if isinstance(run, Mapping) else None
    if not isinstance(run_id, str):
        run_id = str(v_report["run_id"])
    status = Counter(str(r.get("execution_status")) for r in rows)
    d1 = Counter(str(r.get("d1_label_4way")) for r in rows)
    cats = [(lab, float(count), str(count)) for lab, count in sorted(status.items())]
    stem = out_dir / "v_gather_fail_closed_status"
    svg = _svg_bars(
        title="V gather execution_status (fail-closed D0, #23 history)",
        subtitle=(
            f"run `{run_id}` · n_skipped_not_ok="
            f'{v_report.get("n_skipped_not_ok")}/{v_report.get("n_rows")}'
        ),
        categories=cats,
        y_caption="count",
    )
    stem.with_suffix(".svg").write_text(svg + "\n", encoding="utf-8")
    _write_bar_chart_png(
        stem.with_suffix(".png"),
        title="V gather execution_status (fail-closed history)",
        labels=[c[0] for c in cats],
        values=[c[1] for c in cats],
        value_labels=[c[2] for c in cats],
    )
    _write_meta(
        Path(str(stem) + ".meta.json"),
        {
            "figure_id": "v_gather_fail_closed_status",
            "v_run_id": run_id,
            "b2_run_id": B2_RUN,
            "source_predictions": str(FAIL_CLOSED_PRED.relative_to(ROOT)),
            "source_metrics": str(FAIL_CLOSED_METRICS.relative_to(ROOT)),
            "counts_by_execution_status": dict(status),
            "counts_by_d1_label_4way": dict(d1),
            "n_skipped_not_ok": v_report.get("n_skipped_not_ok"),
            "n_scored": v_report.get("n_scored"),
            "scoring_status": v_report.get("scoring_status"),
            "note": (
                "Comparison history (#23): fail-closed gather; auditor does not "
                "load gold D0; all 20 rows are execution_status=failed and "
                "skipped by F-false-endorsement. Tables under "
                "validator_v_gather/ are not overwritten by cited-D0."
            ),
        },
    )


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    out_dir: Path = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = _read_jsonl(V_PRED)
    sidecar = json.loads(V_SIDE.read_text(encoding="utf-8"))
    v_report = json.loads(V_METRICS.read_text(encoding="utf-8"))
    b2_report = json.loads(B2_METRICS.read_text(encoding="utf-8"))
    build_fe_compare(b2_report=b2_report, v_report=v_report, out_dir=out_dir)
    build_v_histograms(
        rows=rows, v_report=v_report, sidecar=sidecar, out_dir=out_dir
    )
    fc_rows = _read_jsonl(FAIL_CLOSED_PRED)
    fc_side = json.loads(FAIL_CLOSED_SIDE.read_text(encoding="utf-8"))
    fc_report = json.loads(FAIL_CLOSED_METRICS.read_text(encoding="utf-8"))
    build_fail_closed_history(
        rows=fc_rows, v_report=fc_report, sidecar=fc_side, out_dir=out_dir
    )
    readme = out_dir / "README.md"
    readme.write_text(
        "# Graphs\n\n"
        "Phase-3 figure drafts generated from checked-in prediction/metrics "
        "files only (`python -m evaluation.phase3_figures`).\n\n"
        "| Figure | Files | Source run_ids |\n"
        "| --- | --- | --- |\n"
        "| FE bar compare (V cited-D0 vs B2 live) | "
        "`fe_bar_v_vs_b2.svg` / `.png` / `.meta.json` | "
        f"`{CITED_D0_RUN}`, `{B2_RUN}` |\n"
        "| V cited-D0 label histogram | "
        "`v_gather_label_histogram.svg` / `.png` / `.meta.json` | "
        f"`{CITED_D0_RUN}` |\n"
        "| V cited-D0 execution status | "
        "`v_gather_cited_d0_status.svg` / `.png` / `.meta.json` | "
        f"`{CITED_D0_RUN}` |\n"
        "| V gather fail-closed status (#23 history) | "
        "`v_gather_fail_closed_status.svg` / `.png` / `.meta.json` | "
        f"`{FAIL_CLOSED_RUN}` |\n\n"
        "Cited-D0 V FE rates are scored (`n_scored=19`, `n_skipped_not_ok=1`). "
        "Fail-closed tables under `docs/paper-assets/tables/validator_v_gather/` "
        "remain comparison history and are not overwritten.\n",
        encoding="utf-8",
    )
    print(f"wrote figures under {out_dir}")


if __name__ == "__main__":
    main()
