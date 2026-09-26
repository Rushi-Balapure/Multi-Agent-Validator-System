"""Architecture, reliability, risk-coverage, cost, and failure figures.

Writes SVG plus a .meta.json sidecar. Missing artifacts produce labelled
placeholders rather than invented numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "paper-assets" / "graphs"


def _svg(width: int, height: int, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">\n{body}\n</svg>\n'
    )


def architecture() -> str:
    boxes = [
        (20, 40, "Reader (blind)"),
        (180, 40, "Judge"),
        (320, 40, "Citation auditor"),
        (180, 140, "Reconciler"),
        (320, 140, "Renderer"),
    ]
    parts = ['<rect width="480" height="220" fill="white"/>']
    for x, y, label in boxes:
        parts.append(f'<rect x="{x}" y="{y}" width="130" height="40" fill="none" stroke="black"/>')
        parts.append(f'<text x="{x + 8}" y="{y + 25}" font-size="12">{label}</text>')
    parts.append('<line x1="150" y1="60" x2="180" y2="60" stroke="black"/>')
    parts.append('<line x1="310" y1="60" x2="320" y2="60" stroke="black"/>')
    parts.append('<line x1="245" y1="80" x2="245" y2="140" stroke="black"/>')
    return _svg(480, 220, "\n".join(parts))


def placeholder_plot(title: str, note: str) -> str:
    return _svg(
        480,
        240,
        (
            '<rect width="480" height="240" fill="white"/>'
            f'<text x="20" y="30" font-size="14">{title}</text>'
            f'<text x="20" y="60" font-size="12">{note}</text>'
            '<line x1="40" y1="200" x2="440" y2="200" stroke="black"/>'
            '<line x1="40" y1="80" x2="40" y2="200" stroke="black"/>'
        ),
    )


def write(name: str, svg: str, meta: dict) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{name}.svg").write_text(svg, encoding="utf-8")
    (OUT / f"{name}.meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    write("architecture", architecture(), {"figure": "architecture", "source": "method diagram"})
    note = "Filled after scored artifacts exist."
    write("reliability", placeholder_plot("Reliability diagram", note), {"figure": "reliability"})
    write("risk_coverage", placeholder_plot("Risk-coverage", note), {"figure": "risk_coverage"})
    write("accuracy_cost", placeholder_plot("Accuracy vs cost", note), {"figure": "accuracy_cost"})
    write("failure_breakdown", placeholder_plot("Failure breakdown", note), {"figure": "failures"})
    print(f"wrote figures under {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
