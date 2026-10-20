"""Error taxonomy over the scored rows of every registered condition.

The taxonomy is declared in advance and derived only from fields the runner
records (predicted label, gold label, four-way labels, rationale codes,
execution status). It separates the two directions that matter:

* **false endorsement** - predicted SUPPORT on a gold non-support claim.
  This is the dangerous error and the preregistered primary metric.
* **missed support** - gold SUPPORT, predicted NEI or REFUTE. This is the
  coverage cost of a conservative system.
* **missed contradiction** - gold REFUTE, predicted SUPPORT or NEI.
* **wrong label, otherwise** - any remaining mismatch.

Rows that failed execution are counted separately and are never scored as a
scientific verdict.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from evaluation.score_predictions import score_predictions_file  # noqa: E402

TABLES = ROOT / "docs" / "paper-assets" / "tables"
PAPER_TABLES = ROOT / "paper" / "tables"
REGISTRY = TABLES / "run_registry.json"

CLASS_ORDER = [
    "false endorsement",
    "missed support",
    "missed contradiction",
    "other label error",
]


def _native_gold(label: str) -> str:
    """SciFact gold uses CONTRADICT; the scored label space uses REFUTE."""
    token = str(label).strip().upper()
    if token == "CONTRADICT":
        return "REFUTE"
    return token


def _classify(pred: str, gold: str) -> str:
    if pred == "SUPPORT" and gold != "SUPPORT":
        return "false endorsement"
    if gold == "SUPPORT":
        return "missed support"
    if gold == "REFUTE":
        return "missed contradiction"
    return "other label error"


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    payload: dict[str, dict] = {}
    for family, family_spec in registry["families"].items():
        payload[family] = {}
        for split_name, conditions in family_spec.items():
            if split_name == "label":
                continue
            split = registry["splits"][split_name]
            payload[family][split_name] = {}
            for condition, directory in conditions.items():
                predictions = ROOT / directory / "predictions.jsonl"
                sidecar = ROOT / directory / "run.json"
                if not predictions.is_file() or not sidecar.is_file():
                    continue
                report = score_predictions_file(predictions, run_sidecar=sidecar, join_gold=split)
                gold_by_id = {
                    item["claim_id"]: item["label_gold"]
                    for item in (report.get("gold_join") or {}).get("claims") or []
                    if item.get("label_gold")
                }
                rows = _read_jsonl(predictions)
                counts: Counter[str] = Counter()
                mechanisms: Counter[str] = Counter()
                n_failed = 0
                n_scored = 0
                n_correct = 0
                for row in rows:
                    status = str(row.get("execution_status") or "ok")
                    if status != "ok":
                        n_failed += 1
                        continue
                    gold = gold_by_id.get(row["claim_id"])
                    if not gold:
                        continue
                    n_scored += 1
                    pred = str(row.get("label"))
                    gold = _native_gold(gold)
                    if pred == gold:
                        n_correct += 1
                        continue
                    counts[_classify(pred, gold)] += 1
                    codes = row.get("rationale_codes") or []
                    if "d0_d1_conflict" in codes:
                        mechanisms["scope conflict"] += 1
                    elif "labels_agree" in codes:
                        mechanisms["scope agreement"] += 1
                    else:
                        mechanisms["no code recorded"] += 1
                payload[family][split_name][condition] = {
                    "n_rows": len(rows),
                    "n_scored": n_scored,
                    "n_correct": n_correct,
                    "n_failed_execution": n_failed,
                    "n_errors": n_scored - n_correct,
                    "error_classes": {name: counts.get(name, 0) for name in CLASS_ORDER},
                    "error_mechanisms": dict(mechanisms),
                }
    out = TABLES / "failure_taxonomy.json"
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    lines = [
        "\\begin{tabular}{lllrr}",
        "\\toprule",
        "Model family & Method & Error class & $n$ & share of errors \\\\",
        "\\midrule",
    ]
    for family, splits in payload.items():
        for split_name, conditions in splits.items():
            for condition, block in conditions.items():
                n_errors = block["n_errors"]
                for name in CLASS_ORDER:
                    count = block["error_classes"].get(name, 0)
                    if not count:
                        continue
                    share = (count / n_errors) if n_errors else 0.0
                    lines.append(
                        " & ".join(
                            [
                                registry["families"][family].get("label", family),
                                f"{condition} ({split_name})",
                                name,
                                str(count),
                                f"{share:.2f}",
                            ]
                        )
                        + " \\\\"
                    )
            lines.append("\\addlinespace[2pt]")
    lines.append("\\bottomrule")
    lines.append("\\end{tabular}")
    PAPER_TABLES.mkdir(parents=True, exist_ok=True)
    (PAPER_TABLES / "t6_failures.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out} and paper/tables/t6_failures.tex")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
