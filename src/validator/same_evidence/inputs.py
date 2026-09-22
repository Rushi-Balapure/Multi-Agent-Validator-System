"""Build same-evidence predict inputs from the locked SciFact corpus.

Predict inputs use Corpus Lock's native claim schema, corpus-document schema,
and the development manifest. A cited document that is not in the corpus is a
join failure. An empty SciFact ``evidence`` object is not a join failure: the
claim is NEI-eligible and the cited abstracts are still attached.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ._repo import ensure_repo_on_path, find_repo_root

_ROOT = ensure_repo_on_path()

from data.scifact_loader import (  # noqa: E402
    MANIFESTS,
    SciFactBundle,
    SciFactDataError,
    ids_sha256,
    load_corpus,
    load_json,
    load_manifest,
    load_split,
    snapshot_hash,
)

NATIVE_LABEL_SPACE = "scifact_SUPPORT_CONTRADICT"
EXPECTED_CORPUS_HASH = "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62"
EXPECTED_MANIFESTS = {
    "source_train": "manifests/scifact/scifact_train_all.json",
    "calibration": "manifests/scifact/scifact_calibration_v1.json",
    "development": "manifests/scifact/scifact_development_v1.json",
    "held_out_local_eval": "manifests/scifact/scifact_held_out_dev_v1.json",
    "official_test_unlabeled": "manifests/scifact/scifact_official_test_v1.json",
}
EXPECTED_COUNTS = {
    "source_train": 809,
    "calibration": 100,
    "development": 709,
    "held_out_local_eval": 300,
    "official_test_unlabeled": 300,
}
_SHA256 = r"^[a-f0-9]{64}$"


class BaselineDataError(RuntimeError):
    """Locked files or a record are inconsistent."""


class MissingEvidenceJoinError(BaselineDataError):
    """D0 citations could not be joined to corpus documents.

    This is not raised for an empty SciFact evidence object. Empty evidence
    means no annotated SUPPORT or CONTRADICT rationales (NEI-eligible).
    """


class Rationale(BaseModel):
    """One native SciFact rationale. Kept off the isolated reader payload."""

    model_config = ConfigDict(extra="forbid")

    label: Literal["SUPPORT", "CONTRADICT"]
    sentences: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def sentence_indexes_are_non_negative(self) -> Rationale:
        if any(index < 0 for index in self.sentences):
            raise ValueError("sentence indexes must be >= 0")
        return self


class GoldEvidenceDoc(BaseModel):
    """One cited corpus document plus any native rationales for that doc."""

    model_config = ConfigDict(extra="forbid")

    doc_id: int
    title: str
    abstract: list[str]
    structured: bool
    rationales: list[Rationale] = Field(default_factory=list)
    snapshot_hash: str = Field(pattern=_SHA256)


class PredictInput(BaseModel):
    """Claim plus joined D0 bundle. ``native_label_space`` is gold, not the prediction."""

    model_config = ConfigDict(extra="forbid")

    claim_id: str = Field(min_length=1)
    split_role: str = Field(min_length=1)
    normalized_claim: str = Field(min_length=1)
    gold_evidence_bundle: list[GoldEvidenceDoc]
    cited_doc_ids: list[int]
    native_label_space: Literal["scifact_SUPPORT_CONTRADICT"]

    @model_validator(mode="after")
    def bundle_matches_citations(self) -> PredictInput:
        joined = [doc.doc_id for doc in self.gold_evidence_bundle]
        if joined != self.cited_doc_ids:
            raise ValueError(
                f"{self.claim_id} gold_evidence_bundle doc ids {joined} "
                f"do not match cited_doc_ids {self.cited_doc_ids}"
            )
        return self

    def nei_eligible(self) -> bool:
        """True when SciFact annotated no SUPPORT or CONTRADICT rationales."""
        return all(not doc.rationales for doc in self.gold_evidence_bundle)


def repo_root() -> Path:
    return find_repo_root()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LoadedInputs(BaseModel):
    """Development claims selected for one baseline run, plus the corpus hash."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    split_role: str
    inputs: list[PredictInput]
    corpus_hash: str = Field(pattern=_SHA256)
    input_source: Literal["corpus_lock"]


def _schema_validator(root: Path, name: str):
    from jsonschema import Draft202012Validator

    schema = load_json(root / "schemas" / name)
    return Draft202012Validator(schema)


def _first_schema_error(validator, instance: object) -> str | None:
    errors = sorted(validator.iter_errors(instance), key=lambda item: str(item))
    if not errors:
        return None
    return errors[0].message


def translate_loader_error(exc: SciFactDataError) -> Exception:
    """Map loader failures onto join errors or other baseline errors.

    ``bundle_claim`` / ``load_split`` raise ``SciFactDataError`` both when a
    cited document is missing and when the evidence object itself is missing.
    Only the first case is a D0 join failure. An empty evidence object does
    not raise.
    """
    text = str(exc)
    if "missing an evidence object" in text:
        return BaselineDataError(
            f"{text} An empty evidence object is NEI-eligible; "
            "a missing evidence object is a loader failure."
        )
    join_markers = (
        "not in corpus.jsonl",
        "missing cited_doc_ids",
        "not in cited_doc_ids",
        "D0 evidence join failed",
    )
    if any(marker in text for marker in join_markers):
        return MissingEvidenceJoinError(text)
    return BaselineDataError(text)


def predict_input_from_bundle(bundle: SciFactBundle, corpus: dict[int, dict]) -> PredictInput:
    """Adapt one loader bundle into the baseline predict input.

    The join itself is ``data.scifact_loader.bundle_claim`` (via ``load_split``).
    This only copies title, abstract, structured, and rationales onto docs the
    loader already attached as same-evidence.
    """
    root = repo_root()
    native_schema = _schema_validator(root, "scifact_claim_native.schema.json")
    doc_schema = _schema_validator(root, "scifact_corpus_doc.schema.json")
    claim_schema = _schema_validator(root, "mavs_claim_record.schema.json")
    evidence_schema = _schema_validator(root, "mavs_evidence_record.schema.json")
    native = bundle.native_claim
    claim_ref = bundle.claim.claim_id
    native_error = _first_schema_error(native_schema, native)
    if native_error:
        raise BaselineDataError(
            f"{claim_ref} failed schemas/scifact_claim_native.schema.json: {native_error}"
        )
    claim_error = _first_schema_error(claim_schema, bundle.claim.model_dump(mode="json"))
    if claim_error:
        raise BaselineDataError(
            f"{claim_ref} failed schemas/mavs_claim_record.schema.json: {claim_error}"
        )
    cited = list(native["cited_doc_ids"])
    evidence = native["evidence"]
    if not isinstance(evidence, dict):
        raise BaselineDataError(
            f"{claim_ref} is missing the evidence object. "
            "An empty evidence object is NEI-eligible; a missing evidence object is a loader failure."
        )
    joined_ids = [int(item.doc_id) for item in bundle.same_evidence]
    if joined_ids != cited:
        raise MissingEvidenceJoinError(
            f"{claim_ref} same-evidence doc ids {joined_ids} do not match cited_doc_ids {cited}; "
            "D0 evidence join failed"
        )
    same_by_doc = {int(item.doc_id): item for item in bundle.same_evidence}
    rationales_by_doc: dict[int, list[Rationale]] = {}
    for key, raw_rationales in evidence.items():
        doc_id = int(key)
        try:
            rationales_by_doc[doc_id] = [Rationale.model_validate(raw) for raw in raw_rationales]
        except ValidationError as exc:
            raise BaselineDataError(f"{claim_ref} doc {doc_id} has a non-native rationale") from exc
    docs: list[GoldEvidenceDoc] = []
    for doc_id in cited:
        if doc_id not in corpus or doc_id not in same_by_doc:
            raise MissingEvidenceJoinError(
                f"{claim_ref} cited doc_id {doc_id} is not in the corpus; D0 evidence join failed. "
                "Empty annotated evidence is NEI-eligible only after cited documents join."
            )
        doc = corpus[doc_id]
        doc_error = _first_schema_error(doc_schema, doc)
        if doc_error:
            raise BaselineDataError(
                f"corpus doc {doc_id} failed schemas/scifact_corpus_doc.schema.json: {doc_error}"
            )
        same = same_by_doc[doc_id]
        evidence_error = _first_schema_error(evidence_schema, same.model_dump(mode="json"))
        if evidence_error:
            raise BaselineDataError(
                f"{claim_ref} doc {doc_id} failed schemas/mavs_evidence_record.schema.json: {evidence_error}"
            )
        if same.snapshot_hash != snapshot_hash(doc):
            raise BaselineDataError(f"{claim_ref} doc {doc_id} snapshot_hash does not match the loader")
        docs.append(
            GoldEvidenceDoc(
                doc_id=doc_id,
                title=doc["title"],
                abstract=list(doc["abstract"]),
                structured=bool(doc["structured"]),
                rationales=rationales_by_doc.get(doc_id, []),
                snapshot_hash=same.snapshot_hash,
            )
        )
    for label in bundle.gold_labels:
        if label.label not in {"SUPPORT", "CONTRADICT"}:
            raise BaselineDataError(
                f"{claim_ref} loader gold label {label.label!r} is outside SUPPORT|CONTRADICT"
            )
    return PredictInput(
        claim_id=claim_ref,
        split_role=bundle.split_role.value,
        normalized_claim=bundle.claim.normalized_claim,
        gold_evidence_bundle=docs,
        cited_doc_ids=cited,
        native_label_space=NATIVE_LABEL_SPACE,
    )


def _assert_corpus_lock(root: Path, corpus_config: str) -> str:
    """Require the Corpus Lock paths and the pinned corpus.jsonl hash."""
    import yaml

    if corpus_config != "configs/corpus/scifact.yaml":
        raise BaselineDataError(
            f"baseline corpus config must be configs/corpus/scifact.yaml, got {corpus_config!r}"
        )
    corpus_cfg = yaml.safe_load((root / corpus_config).read_text(encoding="utf-8"))
    if corpus_cfg.get("corpus_hash") != EXPECTED_CORPUS_HASH:
        raise BaselineDataError(
            "configs/corpus/scifact.yaml corpus_hash is not the locked corpus.jsonl sha256"
        )
    if corpus_cfg.get("raw_dir") != "data/raw/scifact":
        raise BaselineDataError("configs/corpus/scifact.yaml raw_dir is not data/raw/scifact")
    yaml_manifests = corpus_cfg.get("manifests") or {}
    for role, path in EXPECTED_MANIFESTS.items():
        if MANIFESTS.get(role) != path or yaml_manifests.get(role) != path:
            raise BaselineDataError(f"{role} manifest path is not {path}")
        manifest = load_manifest(root / path)
        if manifest.get("locked") is not True:
            raise BaselineDataError(f"{path} is not locked")
        if manifest.get("n_ids") != EXPECTED_COUNTS[role]:
            raise BaselineDataError(
                f"{path} n_ids is {manifest.get('n_ids')!r}, expected {EXPECTED_COUNTS[role]}"
            )
        digest = ids_sha256(manifest["ids"])
        if digest != manifest.get("ids_sha256"):
            raise BaselineDataError(f"{path} ids_sha256 does not match its ids")
    locked = load_json(root / "data" / "pins" / "scifact" / "LOCKED.json")
    pin = load_json(root / "data" / "pins" / "scifact" / "PIN.json")
    if locked.get("locked") is not True:
        raise BaselineDataError("data/pins/scifact/LOCKED.json is not locked")
    if pin.get("split_policy", {}).get("locked") is not True:
        raise BaselineDataError("data/pins/scifact/PIN.json split policy is not locked")
    dev_digest = ids_sha256(load_manifest(root / EXPECTED_MANIFESTS["development"])["ids"])
    if dev_digest != locked.get("manifest_ids_sha256", {}).get("scifact_development_v1"):
        raise BaselineDataError(
            "development ids_sha256 does not match data/pins/scifact/LOCKED.json"
        )
    corpus_path = root / "data" / "raw" / "scifact" / "corpus.jsonl"
    if not corpus_path.is_file():
        raise BaselineDataError(
            "SciFact raw files are missing under data/raw/scifact/. "
            "Run python3 -m data.pins.scifact.download_verify. "
            "The baseline does not download or retrieve documents."
        )
    corpus_hash = sha256_file(corpus_path)
    if corpus_hash != EXPECTED_CORPUS_HASH:
        raise BaselineDataError(
            "corpus.jsonl sha256 does not match the locked corpus hash "
            f"{EXPECTED_CORPUS_HASH}"
        )
    return corpus_hash


def load_development_inputs(
    root: Path,
    limit: int,
    corpus_config: str = "configs/corpus/scifact.yaml",
) -> LoadedInputs:
    """Load the first ``limit`` development claims from ``data.scifact_loader.load_split``."""
    if limit < 1:
        raise BaselineDataError("limit must be at least 1")
    corpus_hash = _assert_corpus_lock(root, corpus_config)
    try:
        bundles = load_split("development", root)
    except SciFactDataError as exc:
        raise translate_loader_error(exc) from exc
    except FileNotFoundError as exc:
        raise BaselineDataError(
            "SciFact raw files are missing under data/raw/scifact/. "
            "Run python3 -m data.pins.scifact.download_verify. "
            "The baseline does not download or retrieve documents."
        ) from exc
    if len(bundles) != EXPECTED_COUNTS["development"]:
        raise BaselineDataError(
            f"load_split('development') returned {len(bundles)} claims, expected 709"
        )
    if limit > len(bundles):
        raise BaselineDataError(f"limit {limit} exceeds the development split ({len(bundles)})")
    corpus = load_corpus(root / "data" / "raw" / "scifact")
    selected = [predict_input_from_bundle(bundle, corpus) for bundle in bundles[:limit]]
    return LoadedInputs(
        split_role="development",
        inputs=selected,
        corpus_hash=corpus_hash,
        input_source="corpus_lock",
    )
