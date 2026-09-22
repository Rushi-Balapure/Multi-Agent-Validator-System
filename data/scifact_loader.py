"""Load SciFact claims and same-evidence gold from the pinned release.

``doc_id`` is the SciFact S2ORC integer. ``snapshot_hash`` is the SHA-256 of
the canonical corpus-document JSON: UTF-8 ``json.dumps`` with sorted keys,
compact separators, and ``ensure_ascii=False``, covering ``doc_id``, ``title``,
``abstract``, and ``structured``.

Manifest ``ids_sha256`` is the SHA-256 of the decimal claim ids, one per line,
including a trailing newline. This loader does not regenerate those ids.

Empty ``evidence`` objects stay unlabeled. They are not four-way Unaddressed
gold. Official test claims have no labels.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC = REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from validator.schemas import (  # noqa: E402
    AccessScope,
    Claim,
    ClaimSource,
    Evidence,
    EvidenceOffsets,
    EvidenceScope,
    GoldProvenance,
    Judgment,
    LabelSpace,
    Provenance,
    SplitRole,
)

PROJECT_ROLES = (
    "calibration",
    "development",
    "held_out_local_eval",
    "official_test_unlabeled",
)

MANIFESTS: dict[str, str] = {
    "source_train": "manifests/scifact/scifact_train_all.json",
    "calibration": "manifests/scifact/scifact_calibration_v1.json",
    "development": "manifests/scifact/scifact_development_v1.json",
    "held_out_local_eval": "manifests/scifact/scifact_held_out_dev_v1.json",
    "official_test_unlabeled": "manifests/scifact/scifact_official_test_v1.json",
}

_CANONICAL_DOC_KEYS = ("abstract", "doc_id", "structured", "title")


class SciFactDataError(RuntimeError):
    """The pinned files, manifests, or a claim record are inconsistent."""


class SciFactBundle(BaseModel):
    """One claim plus its original citations (D0) and any upstream gold spans."""

    model_config = ConfigDict(extra="forbid")

    split_role: SplitRole
    native_claim: dict
    claim: Claim
    same_evidence: list[Evidence] = Field(default_factory=list)
    gold_evidence: list[Evidence] = Field(default_factory=list)
    gold_labels: list[Judgment] = Field(default_factory=list)


def repo_root() -> Path:
    return REPO_ROOT


def ids_sha256(ids: list[int]) -> str:
    """SHA-256 of decimal ids, one per line, with a trailing newline."""
    payload = "".join(f"{claim_id}\n" for claim_id in ids)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_corpus_doc_json(doc: dict) -> str:
    """Stable JSON for one corpus document. Key order does not change the hash."""
    missing = [key for key in _CANONICAL_DOC_KEYS if key not in doc]
    if missing:
        raise SciFactDataError(f"corpus doc {doc.get('doc_id')!r} missing {missing}")
    canonical = {key: doc[key] for key in _CANONICAL_DOC_KEYS}
    return json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def snapshot_hash(doc: dict) -> str:
    """SHA-256 of :func:`canonical_corpus_doc_json` encoded as UTF-8."""
    return hashlib.sha256(canonical_corpus_doc_json(doc).encode("utf-8")).hexdigest()


def gold_span_id(native_claim_id: int, doc_id: int, rationale_index: int) -> str:
    """Reproducible id linking a gold label to one upstream rationale."""
    return f"scifact:{native_claim_id}:{doc_id}:{rationale_index}"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_manifest(path: Path) -> dict:
    manifest = load_json(path)
    ids = manifest.get("ids")
    if not isinstance(ids, list) or any(not isinstance(item, int) for item in ids):
        raise SciFactDataError(f"{path} ids must be a list of integers")
    return manifest


def load_jsonl(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise SciFactDataError(f"{path}:{line_number} is not JSON") from exc
    return records


def index_claims(records: list[dict], source_name: str) -> dict[int, dict]:
    by_id: dict[int, dict] = {}
    for record in records:
        claim_id = record.get("id")
        if not isinstance(claim_id, int):
            raise SciFactDataError(f"{source_name} has a claim without an integer id")
        if claim_id in by_id:
            raise SciFactDataError(f"{source_name} duplicates claim id {claim_id}")
        by_id[claim_id] = record
    return by_id


def load_corpus(raw_dir: Path) -> dict[int, dict]:
    path = raw_dir / "corpus.jsonl"
    docs: dict[int, dict] = {}
    for record in load_jsonl(path):
        doc_id = record.get("doc_id")
        if not isinstance(doc_id, int):
            raise SciFactDataError("corpus.jsonl has a document without an integer doc_id")
        if doc_id in docs:
            raise SciFactDataError(f"corpus.jsonl duplicates doc_id {doc_id}")
        docs[doc_id] = record
    return docs


def abstract_text_and_spans(abstract: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Join abstract sentences with single spaces and record each sentence span."""
    spans: list[tuple[int, int]] = []
    parts: list[str] = []
    pos = 0
    for index, sentence in enumerate(abstract):
        if not isinstance(sentence, str):
            raise SciFactDataError("corpus abstract sentences must be strings")
        spans.append((pos, pos + len(sentence)))
        parts.append(sentence)
        pos += len(sentence)
        if index != len(abstract) - 1:
            parts.append(" ")
            pos += 1
    return "".join(parts), spans


def _require_doc(corpus: dict[int, dict], doc_id: int, claim_id: int) -> dict:
    try:
        return corpus[doc_id]
    except KeyError as exc:
        raise SciFactDataError(
            f"claim {claim_id} cites doc_id {doc_id}, which is not in corpus.jsonl"
        ) from exc


def _document_evidence(doc: dict, digest: str) -> Evidence:
    text, _spans = abstract_text_and_spans(doc["abstract"])
    return Evidence(
        doc_id=doc["doc_id"],
        snapshot_hash=digest,
        text_span=text,
        offsets=EvidenceOffsets(
            start=0,
            end=len(text),
            sentence_idxs=list(range(len(doc["abstract"]))),
        ),
        provenance=Provenance.ORIGINAL,
        deduplication_group=f"s2orc:{doc['doc_id']}",
        access_scope=AccessScope.D0,
    )


def _gold_evidence(
    doc: dict,
    digest: str,
    sentence_idxs: list[int],
) -> Evidence:
    _text, spans = abstract_text_and_spans(doc["abstract"])
    parts: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    for index in sentence_idxs:
        if index >= len(doc["abstract"]):
            raise SciFactDataError(
                f"doc {doc['doc_id']} rationale sentence {index} is outside the abstract"
            )
        parts.append(doc["abstract"][index])
        starts.append(spans[index][0])
        ends.append(spans[index][1])
    return Evidence(
        doc_id=doc["doc_id"],
        snapshot_hash=digest,
        text_span=" ".join(parts),
        offsets=EvidenceOffsets(
            start=min(starts),
            end=max(ends),
            sentence_idxs=list(sentence_idxs),
        ),
        provenance=Provenance.CORPUS_GOLD,
        deduplication_group=f"s2orc:{doc['doc_id']}",
        access_scope=AccessScope.D0,
    )


def bundle_claim(
    native: dict,
    *,
    split_role: str,
    corpus: dict[int, dict],
    hashes: dict[int, str],
) -> SciFactBundle:
    """Build a claim, its D0 citations, and upstream gold when the release has it."""
    role = SplitRole(split_role)
    native_id = native["id"]
    claim_text = native.get("claim")
    if not isinstance(claim_text, str) or not claim_text:
        raise SciFactDataError(f"claim {native_id} is missing claim text")
    claim = Claim(
        claim_id=f"scifact:{native_id}",
        exact_source_span=claim_text,
        normalized_claim=claim_text,
        source=ClaimSource(dataset="scifact", native_id=native_id, split_role=role),
    )
    same_evidence: list[Evidence] = []
    gold_evidence: list[Evidence] = []
    gold_labels: list[Judgment] = []

    cited = native.get("cited_doc_ids")
    if role is not SplitRole.OFFICIAL_TEST_UNLABELED:
        if not isinstance(cited, list):
            raise SciFactDataError(f"claim {native_id} is missing cited_doc_ids")
        for doc_id in cited:
            if not isinstance(doc_id, int):
                raise SciFactDataError(f"claim {native_id} has a non-integer cited doc id")
            doc = _require_doc(corpus, doc_id, native_id)
            same_evidence.append(_document_evidence(doc, hashes[doc_id]))
        evidence = native.get("evidence")
        if not isinstance(evidence, dict):
            raise SciFactDataError(f"claim {native_id} is missing an evidence object")
        for doc_key, rationales in evidence.items():
            doc_id = int(doc_key)
            if doc_id not in cited:
                raise SciFactDataError(
                    f"claim {native_id} gold doc {doc_id} is not in cited_doc_ids"
                )
            doc = _require_doc(corpus, doc_id, native_id)
            if not isinstance(rationales, list):
                raise SciFactDataError(f"claim {native_id} doc {doc_id} rationales are not a list")
            for rationale_index, rationale in enumerate(rationales):
                label = rationale.get("label")
                sentences = rationale.get("sentences")
                if label not in {"SUPPORT", "CONTRADICT"}:
                    raise SciFactDataError(
                        f"claim {native_id} doc {doc_id} has a non-native label {label!r}"
                    )
                if not isinstance(sentences, list) or not sentences:
                    raise SciFactDataError(
                        f"claim {native_id} doc {doc_id} rationale has no sentences"
                    )
                if any(not isinstance(index, int) or index < 0 for index in sentences):
                    raise SciFactDataError(
                        f"claim {native_id} doc {doc_id} has a non-integer sentence index"
                    )
                gold_evidence.append(_gold_evidence(doc, hashes[doc_id], sentences))
                gold_labels.append(
                    Judgment(
                        claim_id=claim.claim_id,
                        evidence_scope=EvidenceScope.NATIVE_SCIFACT,
                        label_space=LabelSpace.SCIFACT_NATIVE,
                        label=label,
                        cited_span_ids=[gold_span_id(native_id, doc_id, rationale_index)],
                        gold_provenance=GoldProvenance.UPSTREAM_SCIFACT,
                    )
                )
    return SciFactBundle(
        split_role=role,
        native_claim=native,
        claim=claim,
        same_evidence=same_evidence,
        gold_evidence=gold_evidence,
        gold_labels=gold_labels,
    )


def load_split(role: str, root: Path | None = None) -> list[SciFactBundle]:
    """Load one locked project split in manifest order.

    ``source_train`` is the id lock for the released training file. It is not a
    project role and is not returned here.
    """
    if role not in PROJECT_ROLES:
        raise SciFactDataError(
            f"{role!r} is not a project split role. "
            "Public SciFact dev is held_out_local_eval. "
            "source_train is only an id lock."
        )
    root = repo_root() if root is None else root
    manifest = load_manifest(root / MANIFESTS[role])
    if manifest.get("role") != role:
        raise SciFactDataError(
            f"{MANIFESTS[role]} role is {manifest.get('role')!r}, expected {role!r}"
        )
    if manifest.get("locked") is not True:
        raise SciFactDataError(f"{manifest.get('manifest_id')} is not locked")
    raw_dir = root / "data" / "raw" / "scifact"
    source_path = raw_dir / manifest["source_file"]
    claims = index_claims(load_jsonl(source_path), manifest["source_file"])
    corpus = load_corpus(raw_dir)
    hashes = {doc_id: snapshot_hash(doc) for doc_id, doc in corpus.items()}
    bundles: list[SciFactBundle] = []
    for claim_id in manifest["ids"]:
        try:
            native = claims[claim_id]
        except KeyError as exc:
            raise SciFactDataError(
                f"{manifest['manifest_id']} id {claim_id} is missing from {manifest['source_file']}"
            ) from exc
        bundles.append(bundle_claim(native, split_role=role, corpus=corpus, hashes=hashes))
    return bundles
