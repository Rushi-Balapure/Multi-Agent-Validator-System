"""Evidence-acquisition metrics for the independent retrieval arm.

For every claim in the frozen development sample this script runs the same
retrieval path the validator uses (``gather_bundle`` over the neutral
question, BM25 over the frozen corpus) and compares the retrieved documents
with two gold sets:

* the *annotated* documents: cited documents that carry a SciFact SUPPORT or
  CONTRADICT rationale;
* the *cited* documents: every document the report cited (D0).

Reported quantities:

``recall_at_k``       mean fraction of annotated documents that appear in the
                      retrieved top-$k$ (claims with no annotated document are
                      excluded from the mean and counted separately);
``precision_at_k``    mean fraction of retrieved documents that are annotated;
``d0_overlap``        mean fraction of retrieved documents that were also
                      cited by the report;
``unique_yield``      mean fraction of annotated documents that retrieval
                      found *and* the report did not cite;
``refuting_yield``    mean fraction of annotated CONTRADICT documents that
                      retrieval found;
``unjudged_rate``     mean fraction of retrieved documents with no annotation.

The gold annotation is used for scoring only. It is never passed to
retrieval, to the reader, or to the judge.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from data.scifact_loader import load_split  # noqa: E402
from validator.claim_sample import claim_ids_from_file  # noqa: E402
from validator.retrieval.config import load_retrieval_config  # noqa: E402
from validator.retrieve import load_claim_texts  # noqa: E402
from validator.runner import gather_bundle  # noqa: E402
from validator.schemas import Claim, ClaimSource, SplitRole  # noqa: E402

SAMPLE = ROOT / "data" / "manifests" / "dev300_seed42.json"
RETRIEVAL_CONFIG = ROOT / "configs" / "retrieval" / "scifact_bm25.yaml"
NEUTRAL_TEMPLATE = ROOT / "prompts" / "validator_v" / "neutral_question_v1.txt"
OUT = ROOT / "docs" / "paper-assets" / "tables" / "retrieval_metrics.json"
K = 8


def _claim(claim_id: str, text: str) -> Claim:
    return Claim(
        claim_id=claim_id,
        normalized_claim=text,
        exact_source_span=text,
        neutral_question=text,
        source=ClaimSource(
            dataset="scifact",
            native_id=int(claim_id.split(":", 1)[1]),
            split_role=SplitRole.DEVELOPMENT,
        ),
    )


def main() -> int:
    claim_ids = claim_ids_from_file(SAMPLE, limit=300)
    retrieval = load_retrieval_config(RETRIEVAL_CONFIG)
    texts = load_claim_texts(claim_ids, retrieval.resolve(retrieval.claims_jsonl))
    template = NEUTRAL_TEMPLATE.read_text(encoding="utf-8")

    split = load_split("development")
    by_id: dict[str, dict] = {}
    for bundle in split:
        native = bundle.native_claim
        native = native if isinstance(native, dict) else native.model_dump()
        by_id[bundle.claim.claim_id] = {
            "cited_doc_ids": list(native.get("cited_doc_ids") or []),
            "evidence": dict(native.get("evidence") or {}),
        }

    recall: list[float] = []
    precision: list[float] = []
    overlap: list[float] = []
    unique: list[float] = []
    refuting: list[float] = []
    unjudged: list[float] = []
    n_annotated_claims = 0
    n_no_annotated = 0
    n_retrieved = 0
    n_d1_docs = 0
    n_d1_annotated = 0
    n_d1_cited = 0
    n_d1_annotated_not_cited = 0
    n_d1_refuting = 0
    per_claim: list[dict] = []

    for claim_id in claim_ids:
        text = texts[claim_id]
        gold = by_id.get(claim_id) or {}
        cited = [int(doc_id) for doc_id in (gold.get("cited_doc_ids") or [])]
        evidence = gold.get("evidence") or {}
        annotated: list[int] = []
        refuting_ids: list[int] = []
        for raw_doc_id, rationales in evidence.items():
            doc_id = int(raw_doc_id)
            labels = {
                item.get("label")
                for item in (rationales or [])
                if isinstance(item, dict)
            }
            if labels & {"SUPPORT", "CONTRADICT"}:
                annotated.append(doc_id)
                if "CONTRADICT" in labels:
                    refuting_ids.append(doc_id)
        claim = _claim(claim_id, text)
        claim = claim.model_copy(update={"neutral_question": template.replace("{claim}", text)})
        bundle = gather_bundle(claim, retrieval)
        retrieved = [passage.doc_id for passage in bundle.passages][:K]

        n_retrieved += 1
        n_d1_docs += len(retrieved)
        n_d1_annotated += sum(1 for doc_id in retrieved if doc_id in annotated)
        n_d1_cited += sum(1 for doc_id in retrieved if doc_id in cited)
        n_d1_annotated_not_cited += sum(
            1 for doc_id in retrieved if doc_id in annotated and doc_id not in cited
        )
        n_d1_refuting += sum(1 for doc_id in retrieved if doc_id in refuting_ids)

        if annotated:
            n_annotated_claims += 1
            hit = sum(1 for doc_id in annotated if doc_id in retrieved)
            recall.append(hit / len(annotated))
            unique.append(
                sum(1 for doc_id in annotated if doc_id in retrieved and doc_id not in cited)
                / len(annotated)
            )
            refuting.append(
                (
                    sum(1 for doc_id in refuting_ids if doc_id in retrieved) / len(refuting_ids)
                    if refuting_ids
                    else 0.0
                )
            )
        else:
            n_no_annotated += 1
            unique.append(0.0)
            refuting.append(0.0)
        precision.append(
            (sum(1 for doc_id in retrieved if doc_id in annotated) / len(retrieved))
            if retrieved
            else 0.0
        )
        overlap.append(
            (sum(1 for doc_id in retrieved if doc_id in cited) / len(retrieved)) if retrieved else 0.0
        )
        unjudged.append(
            (sum(1 for doc_id in retrieved if doc_id not in annotated) / len(retrieved))
            if retrieved
            else 0.0
        )
        per_claim.append(
            {
                "claim_id": claim_id,
                "n_retrieved": len(retrieved),
                "n_annotated": len(annotated),
                "n_cited": len(cited),
                "n_hit": sum(1 for doc_id in annotated if doc_id in retrieved),
                "n_overlap": sum(1 for doc_id in retrieved if doc_id in cited),
                "n_unique": sum(
                    1 for doc_id in annotated if doc_id in retrieved and doc_id not in cited
                ),
            }
        )

    payload = {
        "formula_ids": ["F-recall-at-k"],
        "split": "development",
        "sample": str(SAMPLE.relative_to(ROOT)),
        "k": K,
        "n_claims": n_retrieved,
        "n_claims_with_annotated_evidence": n_annotated_claims,
        "n_claims_without_annotated_evidence": n_no_annotated,
        "recall_at_k": mean(recall) if recall else 0.0,
        "precision_at_k": mean(precision) if precision else 0.0,
        "d0_overlap": mean(overlap) if overlap else 0.0,
        "unique_yield": mean(unique) if unique else 0.0,
        "refuting_yield": mean(refuting) if refuting else 0.0,
        "unjudged_rate": mean(unjudged) if unjudged else 0.0,
        "micro": {
            "n_retrieved_documents": n_d1_docs,
            "n_annotated_retrieved": n_d1_annotated,
            "n_cited_retrieved": n_d1_cited,
            "n_annotated_retrieved_not_cited": n_d1_annotated_not_cited,
            "n_refuting_retrieved": n_d1_refuting,
        },
        "per_claim": per_claim,
        "note": (
            "Gold annotations are used for scoring only and are never passed to "
            "retrieval, the reader, or the judge."
        ),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {OUT} recall@k={payload['recall_at_k']:.3f} "
        f"overlap={payload['d0_overlap']:.3f} unique={payload['unique_yield']:.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
