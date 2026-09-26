"""Score B2 vs V, attach cited-doc families, and run the paired bootstrap."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluation.bootstrap import BootstrapByFamilyConfig, bootstrap_by_family
from evaluation.families import attach_claim_families, families_from_split
from evaluation.failures import breakdown
from evaluation.score_predictions import score_predictions_file


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def compare(
    *,
    b2_predictions: Path,
    v_predictions: Path,
    b2_sidecar: Path | None,
    v_sidecar: Path | None,
    split: str,
    n_resamples: int = 2000,
    seed: int = 0,
) -> dict[str, Any]:
    b2_report = score_predictions_file(
        b2_predictions, run_sidecar=b2_sidecar, join_gold=split
    )
    v_report = score_predictions_file(
        v_predictions, run_sidecar=v_sidecar, join_gold=split
    )
    b2_rows = _read_jsonl(b2_predictions)
    v_rows = _read_jsonl(v_predictions)
    gold_by_id = {
        item["claim_id"]: item["label_gold"]
        for item in (b2_report.get("gold_join") or {}).get("claims") or []
        if item.get("label_gold")
    }
    if not gold_by_id:
        from evaluation.scifact_gold import join_scifact_gold

        joined, _ = join_scifact_gold(b2_rows, split=split)
        gold_by_id = {row["claim_id"]: row["label_gold"] for row in joined}
        b2_rows = joined
        v_joined, _ = join_scifact_gold(v_rows, split=split)
        v_rows = v_joined
    else:
        for row in b2_rows:
            row.setdefault("label_gold", gold_by_id.get(row["claim_id"]))
        for row in v_rows:
            row.setdefault("label_gold", gold_by_id.get(row["claim_id"]))
    families = families_from_split(split, [row["claim_id"] for row in b2_rows])
    b2_rows = attach_claim_families(b2_rows, families)
    v_rows = attach_claim_families(v_rows, families)
    bootstrap = bootstrap_by_family(
        {"B2": b2_rows, "V": v_rows},
        config=BootstrapByFamilyConfig(n_resamples=n_resamples, seed=seed),
    )
    return {
        "split": split,
        "b2": b2_report,
        "v": v_report,
        "bootstrap": bootstrap,
        "v_failures": breakdown(v_rows),
        "n_families": bootstrap["n_families"],
        "family_source": bootstrap["family_source"],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paired B2 vs V score and bootstrap.")
    parser.add_argument("--b2-predictions", type=Path, required=True)
    parser.add_argument("--v-predictions", type=Path, required=True)
    parser.add_argument("--b2-sidecar", type=Path, default=None)
    parser.add_argument("--v-sidecar", type=Path, default=None)
    parser.add_argument("--join-gold", default="development")
    parser.add_argument("--n-resamples", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    report = compare(
        b2_predictions=args.b2_predictions,
        v_predictions=args.v_predictions,
        b2_sidecar=args.b2_sidecar,
        v_sidecar=args.v_sidecar,
        split=args.join_gold,
        n_resamples=args.n_resamples,
        seed=args.seed,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {args.output} families={report['n_families']} source={report['family_source']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
