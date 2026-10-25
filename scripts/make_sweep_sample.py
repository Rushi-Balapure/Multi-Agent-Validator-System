#!/usr/bin/env python3
"""Build the fixed stratified subset used for the multi-model sweep.

The primary comparison runs on the full 300-claim development sample. The
sweep repeats the same B2-versus-V pairing on a small, label-balanced subset
so that eleven model families can be measured inside a fixed API budget.

Sampling rule: take the frozen 300-claim development sample, join each claim
to its SciFact gold label, shuffle the ids of each label class with seed 42,
and take the first ``--per-class`` ids. The result depends only on the frozen
manifest, the pinned gold release, and the seed.

The output is a locked claim sample: native ids, their hash, the source
manifest, and the label distribution, in the same schema the runners use.

Usage:
    .venv-mavs/bin/python scripts/make_sweep_sample.py \
        --out data/manifests/sweep30_seed42.json --per-class 10
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from data.scifact_loader import load_split  # noqa: E402
from validator.claim_sample import build_claim_sample  # noqa: E402
from validator.retrieve import native_id_from_claim_id  # noqa: E402


def native_label(bundle) -> str:
    labels = {judgment.label for judgment in bundle.gold_labels}
    if "CONTRADICT" in labels:
        return "CONTRADICT"
    if "SUPPORT" in labels:
        return "SUPPORT"
    return "NEI"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", default="data/manifests/dev300_seed42.json")
    parser.add_argument("--out", default="data/manifests/sweep30_seed42.json")
    parser.add_argument("--per-class", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    source_path = ROOT / args.source
    source = json.loads(source_path.read_text())
    wanted = source["claim_ids"]
    bundles = {bundle.claim.claim_id: bundle for bundle in load_split("development")}
    missing = [claim_id for claim_id in wanted if claim_id not in bundles]
    if missing:
        raise SystemExit(f"claims missing from the pinned release: {missing[:5]}")

    by_label: dict[str, list[str]] = {"SUPPORT": [], "CONTRADICT": [], "NEI": []}
    for claim_id in wanted:
        by_label[native_label(bundles[claim_id])].append(claim_id)

    rng = random.Random(args.seed)
    selected: list[str] = []
    for label in ("SUPPORT", "CONTRADICT", "NEI"):
        pool = sorted(by_label[label])
        rng.shuffle(pool)
        selected.extend(pool[: args.per_class])
    selected.sort(key=wanted.index)

    counts = Counter(native_label(bundles[claim_id]) for claim_id in selected)
    sample = build_claim_sample(
        sample_id=Path(args.out).stem,
        split_role="development",
        seed=args.seed,
        native_ids=[native_id_from_claim_id(claim_id) for claim_id in selected],
        source_manifest=str(source_path.resolve()),
        label_distribution=dict(counts),
    )
    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sample.model_dump(), indent=2) + "\n")
    print(f"wrote {out} with {sample.n_ids} claims {dict(counts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
