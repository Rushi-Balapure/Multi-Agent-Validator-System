"""Independent gatherer for the locked SciFact corpus.

``gather`` accepts a claim text or neutral question, a retrieval config, and a
project ``claim_id`` such as ``scifact:2``. It does not accept gold labels,
original citations, asserted answers, or conclusions.

Query protocol for this round: open inquiry, scope/measurement, and
limitations-or-null-results. Each form keeps the top 20 positive BM25 hits.
Those lists are deduped, reranked by the best BM25 score, and cut to at most
8 passages. ``retrieval_round`` stays 1. Round-2 stop rules and
reciprocal-rank fusion are config prep only (``round2`` / ``rrf`` locked
off). Dense retrieval is not in this MR.

From the repository root::

    PYTHONPATH=src python3 -m validator.retrieve index \\
        --config configs/retrieval/scifact_bm25.yaml
    PYTHONPATH=src python3 -m validator.retrieve gather-claims \\
        --config configs/retrieval/scifact_bm25.yaml \\
        --limit 5 \\
        --output artifacts/retrieval/dev5_bundles.jsonl
    PYTHONPATH=src python3 -m validator.retrieve gather-dev10 \\
        --config configs/retrieval/scifact_bm25.yaml \\
        --output artifacts/retrieval/dev10_bundles.jsonl

After ``pip install -e .`` the same commands are ``mavs-retrieve index``,
``mavs-retrieve gather-claims``, and ``mavs-retrieve gather-dev10``.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from validator.retrieval.paths import REPO_ROOT
from validator.retrieval.bm25 import BM25Index, ensure_index, tokenize
from validator.retrieval.config import RetrievalConfig, load_retrieval_config, verify_corpus_lock
from validator.retrieval.errors import RetrievalError
from validator.retrieval.models import (
    PASSAGE_CEILING,
    TOP_K_CEILING,
    EvidenceBundle,
    QueryHit,
    QueryLog,
    RetrievedPassage,
    normalize_passage_text,
)
from validator.schemas import AccessScope, EvidenceOffsets, Provenance

_CLAIM_ID = re.compile(r"^scifact:(\d+)$")
_CORPUS_CACHE: dict[tuple, dict[int, dict]] = {}


@dataclass
class _Candidate:
    doc_id: int
    score: float
    query: str


def project_claim_id(native_id: int) -> str:
    """Match the corpus-lock loader, which stamps ``scifact:{native_id}``."""
    if not isinstance(native_id, int) or isinstance(native_id, bool) or native_id < 0:
        raise RetrievalError(f"native claim id must be a non-negative integer, got {native_id!r}")
    return f"scifact:{native_id}"


def native_id_from_claim_id(claim_id: str) -> int:
    if not isinstance(claim_id, str):
        raise RetrievalError(f"claim_id must be a project id string, got {claim_id!r}")
    match = _CLAIM_ID.fullmatch(claim_id)
    if match is None:
        raise RetrievalError(f"claim_id must look like scifact:2, got {claim_id!r}")
    return int(match.group(1))


def project_claim_ids_from_manifest(path: Path, count: int = 10) -> list[str]:
    from data.scifact_loader import load_manifest

    manifest = load_manifest(path)
    native_ids = manifest["ids"]
    if len(native_ids) < count:
        raise RetrievalError(f"{path} has {len(native_ids)} ids; need {count}")
    return [project_claim_id(native_id) for native_id in native_ids[:count]]


def assert_fixed_claim_ids(config: RetrievalConfig) -> list[str]:
    """Require the config pin to be the first 10 development manifest ids."""
    derived = project_claim_ids_from_manifest(config.resolve(config.development_manifest))
    pinned = list(config.fixed_claim_ids)
    if pinned != derived:
        raise RetrievalError(
            "fixed_claim_ids must be the first 10 development manifest ids "
            "in project form scifact:{native_id}. "
            f"pinned={pinned} manifest={derived}"
        )
    return pinned


def load_claim_texts(claim_ids: list[str], claims_path: Path) -> dict[str, str]:
    """Load claim strings only. Gold fields on the JSONL records are ignored."""
    from data.scifact_loader import index_claims, load_jsonl

    by_native = index_claims(load_jsonl(claims_path), claims_path.name)
    texts: dict[str, str] = {}
    for claim_id in claim_ids:
        native_id = native_id_from_claim_id(claim_id)
        try:
            record = by_native[native_id]
        except KeyError as exc:
            raise RetrievalError(f"{claim_id} is missing from {claims_path}") from exc
        text = record.get("claim")
        if not isinstance(text, str) or not text.strip():
            raise RetrievalError(f"{claim_id} is missing claim text")
        texts[claim_id] = text
    return texts


def build_query_forms(text: str, config: RetrievalConfig) -> list[tuple[str, str]]:
    templates = config.query_templates
    forms = (
        ("open_inquiry", templates.open_inquiry),
        ("scope_measurement", templates.scope_measurement),
        ("limitations_null", templates.limitations_null),
    )
    return [(name, template.replace("{text}", text)) for name, template in forms]


def _load_corpus(config: RetrievalConfig) -> dict[int, dict]:
    from data.scifact_loader import load_corpus

    path = config.resolve(config.corpus_jsonl)
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size, config.corpus_hash)
    cached = _CORPUS_CACHE.get(key)
    if cached is not None:
        return cached
    corpus = load_corpus(path.parent)
    _CORPUS_CACHE[key] = corpus
    return corpus


def _positive_hits(index: BM25Index, query: str, top_k: int) -> list[tuple[int, float]]:
    found = [(doc_id, score) for doc_id, score in index.search(query, top_k) if score > 0]
    return found[:top_k]


def _rerank_union(
    per_doc: dict[int, _Candidate],
    corpus: dict[int, dict],
    limit: int,
) -> list[_Candidate]:
    """Dedupe by document id and normalized abstract, then keep the best scores.

    Round 2 is not selected here. ``RetrievalConfig.round2`` and ``.rrf`` are
    locked off. Reciprocal-rank fusion would be ``1 / (rrf.k + rank)`` summed
    across lists; this rerank is max BM25 only.
    """
    from data.scifact_loader import abstract_text_and_spans

    grouped: dict[str, _Candidate] = {}
    for candidate in per_doc.values():
        try:
            doc = corpus[candidate.doc_id]
        except KeyError as exc:
            raise RetrievalError(
                f"doc_id {candidate.doc_id} is in the index and not in the corpus"
            ) from exc
        text, _spans = abstract_text_and_spans(doc["abstract"])
        key = normalize_passage_text(text)
        current = grouped.get(key)
        if current is None or candidate.score > current.score or (
            candidate.score == current.score and candidate.doc_id < current.doc_id
        ):
            grouped[key] = candidate
    ordered = sorted(grouped.values(), key=lambda item: (-item.score, item.doc_id))
    return ordered[:limit]


def _passage(
    doc: dict,
    index: BM25Index,
    candidate: _Candidate,
    rank: int,
    retrieval_round: int,
) -> RetrievedPassage:
    from data.scifact_loader import abstract_text_and_spans, snapshot_hash

    digest = snapshot_hash(doc)
    stored = index.snapshot_by_id.get(doc["doc_id"])
    if digest != stored:
        raise RetrievalError(
            f"snapshot_hash for doc_id {doc['doc_id']} does not match the index"
        )
    text, _spans = abstract_text_and_spans(doc["abstract"])
    if not math.isfinite(candidate.score):
        raise RetrievalError(f"non-finite BM25 score for doc_id {doc['doc_id']}")
    return RetrievedPassage(
        doc_id=doc["doc_id"],
        snapshot_hash=digest,
        text_span=text,
        offsets=EvidenceOffsets(
            start=0,
            end=len(text),
            sentence_idxs=list(range(len(doc["abstract"]))),
        ),
        query=candidate.query,
        rank=rank,
        retrieval_round=retrieval_round,
        provenance=Provenance.INDEPENDENT,
        deduplication_group=f"s2orc:{doc['doc_id']}",
        access_scope=AccessScope.D1,
        score=candidate.score,
    )


def gather(
    claim_or_neutral_question: str,
    config: RetrievalConfig,
    claim_id: str,
) -> EvidenceBundle:
    """Retrieve an independent EvidenceBundle for one claim text or neutral question."""
    if not isinstance(claim_or_neutral_question, str):
        raise TypeError(
            "gather accepts a claim text or neutral question string, not gold records"
        )
    if not isinstance(config, RetrievalConfig):
        raise TypeError("config must be a RetrievalConfig")
    if not isinstance(claim_id, str):
        raise TypeError("claim_id must be a project id string such as scifact:2")
    if not claim_or_neutral_question.strip():
        raise ValueError("claim text or neutral question is empty")
    native_id_from_claim_id(claim_id)
    if not tokenize(claim_or_neutral_question):
        raise ValueError("claim text or neutral question has no alnum tokens")

    verify_corpus_lock(config)
    index = ensure_index(config)
    if index.corpus_hash != config.corpus_hash:
        raise RetrievalError("loaded index corpus_hash does not match the retrieval config")
    corpus = _load_corpus(config)
    if index.n_docs != len(corpus) or any(doc_id not in corpus for doc_id in index.doc_ids):
        raise RetrievalError(
            f"index has {index.n_docs} documents and the corpus has {len(corpus)}; refusing to gather"
        )

    per_query_limit = min(config.top_k_per_query, TOP_K_CEILING)
    passage_limit = min(config.max_passages, PASSAGE_CEILING)
    logs: list[QueryLog] = []
    per_doc: dict[int, _Candidate] = {}
    for form, query in build_query_forms(claim_or_neutral_question, config):
        hits: list[QueryHit] = []
        for rank, (doc_id, score) in enumerate(
            _positive_hits(index, query, per_query_limit),
            start=1,
        ):
            hits.append(QueryHit(doc_id=doc_id, rank=rank, score=score))
            current = per_doc.get(doc_id)
            if current is None or score > current.score:
                per_doc[doc_id] = _Candidate(doc_id=doc_id, score=score, query=query)
        logs.append(QueryLog(form=form, query=query, hits=hits))

    chosen = _rerank_union(per_doc, corpus, passage_limit)
    passages = [
        _passage(corpus[candidate.doc_id], index, candidate, rank, config.retrieval_round)
        for rank, candidate in enumerate(chosen, start=1)
    ]
    return EvidenceBundle(
        claim_id=claim_id,
        query=claim_or_neutral_question,
        queries=logs,
        retrieval_round=config.retrieval_round,
        corpus_hash=config.corpus_hash,
        passages=passages,
    )


def format_bundle_log(bundle: EvidenceBundle) -> str:
    lines = [
        f"claim_id={bundle.claim_id} retrieval_round={bundle.retrieval_round} "
        f"passages={len(bundle.passages)} corpus_hash={bundle.corpus_hash}"
    ]
    for item in bundle.queries:
        hits = ",".join(f"{hit.doc_id}@{hit.rank}" for hit in item.hits)
        logged_query = " ".join(item.query.split())
        lines.append(f"form={item.form} query={logged_query} hits={hits}")
    ranked = ",".join(
        f"{passage.doc_id}@{passage.rank}" for passage in bundle.passages
    )
    lines.append(f"reranked={ranked}")
    return "\n".join(lines)


def _read_bundles(path: Path) -> list[EvidenceBundle]:
    bundles: list[EvidenceBundle] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            bundles.append(EvidenceBundle.model_validate_json(line))
        except ValidationError as exc:
            raise RetrievalError(f"{path}:{line_number} is not an EvidenceBundle") from exc
    return bundles


def _split_claim_ids(value: str) -> list[str]:
    if not isinstance(value, str) or not value.strip():
        raise RetrievalError("--claim-ids was empty")
    parts = [part.strip() for part in value.split(",")]
    if any(part == "" for part in parts):
        raise RetrievalError(f"--claim-ids has an empty id: {value!r}")
    return parts


def resolve_gather_claim_ids(
    config: RetrievalConfig,
    *,
    claim_ids: str | list[str] | None = None,
    manifest: Path | None = None,
    claim_ids_file: Path | None = None,
    limit: int | None = None,
) -> list[str]:
    """Resolve project claim ids for ``gather-claims``.

    ``--claim-ids`` or ``--claim-ids-file`` selects those ids. Otherwise
    take the first ``limit`` ids (default 5) from ``manifest`` or the
    locked development manifest. Pass only one of ``--claim-ids``,
    ``--claim-ids-file``, and ``--manifest``. ``limit`` caps an explicit
    id list.
    """
    if not isinstance(config, RetrievalConfig):
        raise TypeError("config must be a RetrievalConfig")
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise RetrievalError("--limit must be a positive integer")
    supplied = [item is not None for item in (claim_ids, manifest, claim_ids_file)]
    if sum(supplied) > 1:
        raise RetrievalError("pass only one of --claim-ids, --claim-ids-file, and --manifest")
    if claim_ids_file is not None:
        from validator.claim_sample import ClaimSampleError, claim_ids_from_file

        try:
            selected = claim_ids_from_file(claim_ids_file, limit=limit)
        except ClaimSampleError as exc:
            raise RetrievalError(str(exc)) from exc
    elif claim_ids is None:
        count = 5 if limit is None else limit
        path = manifest if manifest is not None else config.resolve(config.development_manifest)
        selected = project_claim_ids_from_manifest(path, count)
    else:
        selected = _split_claim_ids(claim_ids) if isinstance(claim_ids, str) else list(claim_ids)
        if limit is not None:
            selected = selected[:limit]
    if not selected:
        raise RetrievalError("no claim ids to gather")
    if len(selected) != len(set(selected)):
        raise RetrievalError(f"duplicate claim ids: {selected}")
    for claim_id in selected:
        native_id_from_claim_id(claim_id)
    return selected


def run_gather_claims(
    config: RetrievalConfig,
    output: Path,
    claim_ids: list[str],
    *,
    download: bool = True,
) -> list[EvidenceBundle]:
    """Gather claim texts for ``claim_ids`` and write JSONL EvidenceBundles.

    Claim text comes from :func:`load_claim_texts` only. Gold fields on the
    claims file are not passed to :func:`gather`.
    """
    if not isinstance(claim_ids, list) or not claim_ids:
        raise RetrievalError("claim_ids must be a non-empty list of project ids")
    resolved = resolve_gather_claim_ids(config, claim_ids=claim_ids)
    if resolved != claim_ids:
        raise RetrievalError("claim_ids drifted while resolving")
    if download:
        from data.pins.scifact.download_verify import ensure_scifact_raw

        ensure_scifact_raw(REPO_ROOT)
    texts = load_claim_texts(claim_ids, config.resolve(config.claims_jsonl))
    bundles: list[EvidenceBundle] = []
    for claim_id in claim_ids:
        bundle = gather(texts[claim_id], config, claim_id)
        if bundle.claim_id != claim_id or bundle.query != texts[claim_id]:
            raise RetrievalError(f"{claim_id} bundle was not keyed by the claim text")
        bundles.append(bundle)
        print(format_bundle_log(bundle), flush=True)
    if [bundle.claim_id for bundle in bundles] != claim_ids:
        raise RetrievalError("bundle claim_ids drifted from the requested ids")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for bundle in bundles:
            handle.write(
                json.dumps(
                    bundle.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
            handle.write("\n")
    written = _read_bundles(output)
    if [bundle.claim_id for bundle in written] != claim_ids:
        raise RetrievalError(f"{output} claim_ids do not match the requested ids")
    print(f"wrote {len(written)} bundles {output}", flush=True)
    return written


def run_gather_dev10(
    config: RetrievalConfig,
    output: Path,
    *,
    download: bool = True,
) -> list[EvidenceBundle]:
    """Gather the 10 pinned development claims and write JSONL bundles."""
    if download:
        from data.pins.scifact.download_verify import ensure_scifact_raw

        ensure_scifact_raw(REPO_ROOT)
    pinned = assert_fixed_claim_ids(config)
    return run_gather_claims(config, output, pinned, download=False)


def _resolve_cli_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    rooted = (REPO_ROOT / path).resolve()
    if rooted.exists() or not path.exists():
        return rooted
    return path.resolve()


def main(argv: list[str] | None = None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--config",
        default="configs/retrieval/scifact_bm25.yaml",
        help="Retrieval YAML. Relative paths are resolved from the repository root.",
    )
    parser = argparse.ArgumentParser(
        prog="python3 -m validator.retrieve",
        description=(
            "Build a reproducible SciFact BM25 index and gather independent D1 "
            "evidence. gather-claims takes arbitrary project claim ids; "
            "gather-dev10 keeps the 10 pinned development ids."
        ),
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser(
        "index",
        parents=[common],
        help="Verify corpus_hash and write the BM25 index.",
    )
    gather_command = subcommands.add_parser(
        "gather-dev10",
        parents=[common],
        help="Write EvidenceBundles for the 10 pinned development claim ids.",
    )
    gather_command.add_argument(
        "--output",
        default="artifacts/retrieval/dev10_bundles.jsonl",
        help="JSONL path. Relative paths are resolved from the repository root.",
    )
    claims_command = subcommands.add_parser(
        "gather-claims",
        parents=[common],
        help=(
            "Write EvidenceBundles for --claim-ids or a manifest prefix. "
            "Default: first 5 locked development ids."
        ),
    )
    claims_command.add_argument(
        "--claim-ids",
        default=None,
        help=(
            "Comma-separated project ids, such as scifact:0,scifact:2. "
            "Do not combine with --manifest."
        ),
    )
    claims_command.add_argument(
        "--manifest",
        default=None,
        help=(
            "Manifest JSON of native ids. Default: the locked development "
            "manifest. Do not combine with --claim-ids or --claim-ids-file."
        ),
    )
    claims_command.add_argument(
        "--claim-ids-file",
        default=None,
        help=(
            "Frozen sample JSON with claim_ids. Do not combine with "
            "--claim-ids or --manifest."
        ),
    )
    claims_command.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Manifest prefix length (default 5 when --claim-ids is omitted). "
            "When --claim-ids is set, keep only the first N of those ids."
        ),
    )
    claims_command.add_argument(
        "--output",
        default="artifacts/retrieval/dev5_bundles.jsonl",
        help="JSONL path. Relative paths are resolved from the repository root.",
    )
    args = parser.parse_args(argv)
    try:
        config = load_retrieval_config(_resolve_cli_path(args.config))
        if args.command == "index":
            from validator.retrieval.bm25 import build_index

            index = build_index(config)
            print(
                f"index_path={config.resolve(config.index_path)} "
                f"n_docs={index.n_docs} corpus_hash={index.corpus_hash}",
                flush=True,
            )
            return 0
        output = _resolve_cli_path(args.output)
        if args.command == "gather-dev10":
            run_gather_dev10(config, output)
            return 0
        manifest = None if args.manifest is None else _resolve_cli_path(args.manifest)
        claim_ids_file = (
            None if args.claim_ids_file is None else _resolve_cli_path(args.claim_ids_file)
        )
        claim_ids = resolve_gather_claim_ids(
            config,
            claim_ids=args.claim_ids,
            manifest=manifest,
            claim_ids_file=claim_ids_file,
            limit=args.limit,
        )
        run_gather_claims(config, output, claim_ids)
        return 0
    except (RetrievalError, ValidationError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        from data.pins.scifact.download_verify import PinMismatch
        from data.scifact_loader import SciFactDataError

        if isinstance(exc, (PinMismatch, SciFactDataError)):
            print(f"error: {exc}", file=sys.stderr)
            return 2
        raise


if __name__ == "__main__":
    raise SystemExit(main())
