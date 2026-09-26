"""Write the frozen 300-claim development sample (seed 42).

Does not touch the held-out 300. Label distribution is filled only when
``data/raw/scifact/claims_train.jsonl`` is present.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data.scifact_loader import load_jsonl  # noqa: E402
from evaluation.scifact_gold import claim_label_from_native  # noqa: E402
from validator.claim_sample import dump_claim_sample, sample_from_manifest  # noqa: E402

SEED = 42
N = 300
OUTPUT = ROOT / "data" / "manifests" / "dev300_seed42.json"
MANIFEST = ROOT / "manifests" / "scifact" / "scifact_development_v1.json"
CLAIMS = ROOT / "data" / "raw" / "scifact" / "claims_train.jsonl"


def _label_distribution(native_ids: list[int]) -> dict[str, int] | None:
    if not CLAIMS.is_file():
        return None
    wanted = set(native_ids)
    counts: Counter[str] = Counter()
    for record in load_jsonl(CLAIMS):
        claim_id = record.get("id")
        if claim_id not in wanted:
            continue
        evidence = record.get("evidence") or {}
        labels: list[str] = []
        if isinstance(evidence, dict):
            for raw_rationales in evidence.values():
                if not isinstance(raw_rationales, list):
                    continue
                for rationale in raw_rationales:
                    if isinstance(rationale, dict) and isinstance(rationale.get("label"), str):
                        labels.append(rationale["label"])
        counts[claim_label_from_native(labels)] += 1
    if sum(counts.values()) != len(native_ids):
        return None
    return {"SUPPORT": counts["SUPPORT"], "CONTRADICT": counts["CONTRADICT"], "NEI": counts["NEI"]}


def main() -> int:
    sample = sample_from_manifest(
        MANIFEST,
        sample_id="dev300_seed42",
        split_role="development",
        n=N,
        seed=SEED,
        label_distribution=None,
    )
    distribution = _label_distribution(sample.native_ids)
    if distribution is not None:
        sample = sample.model_copy(update={"label_distribution": distribution})
    dump_claim_sample(sample, OUTPUT)
    print(f"wrote {OUTPUT} n={sample.n_ids} seed={sample.seed} ids_sha256={sample.ids_sha256}")
    if sample.label_distribution:
        print(f"label_distribution={sample.label_distribution}")
    else:
        print("label_distribution=null (claims_train.jsonl missing or incomplete)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
