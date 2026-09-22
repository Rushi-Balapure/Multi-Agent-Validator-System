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
    ids_sha256,
    index_claims,
    load_corpus,
    load_json,
    load_jsonl,
    load_manifest,
    snapshot_hash,
)

NATIVE_LABEL_SPACE = "scifact_SUPPORT_CONTRADICT"
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
    input_source: Literal["corpus_lock", "override"]


def _schema_validator(root: Path, name: str):
    from jsonschema import Draft202012Validator

    schema = load_json(root / "schemas" / name)
    return Draft202012Validator(schema)


def _first_schema_error(validator, instance: object) -> str | None:
    errors = sorted(validator.iter_errors(instance), key=lambda item: str(item))
    if not errors:
        return None
    return errors[0].message


def build_predict_input(
    native: dict,
    *,
    split_role: str,
    corpus: dict[int, dict],
    claim_schema,
    doc_schema,
) -> PredictInput:
    """Join one native claim to D0 corpus documents.

    Raises ``MissingEvidenceJoinError`` when cited docs cannot be joined.
    An empty ``evidence`` object still returns a bundle of the cited docs.
    """
    native_id = native.get("id")
    claim_ref = f"scifact:{native_id}"
    if "cited_doc_ids" not in native or not isinstance(native.get("cited_doc_ids"), list):
        raise MissingEvidenceJoinError(
            f"{claim_ref} is missing cited_doc_ids; D0 evidence join cannot run"
        )
    if "evidence" not in native or not isinstance(native.get("evidence"), dict):
        raise BaselineDataError(
            f"{claim_ref} is missing the evidence object. "
            "An empty object would be NEI-eligible; a missing field is a loader failure."
        )
    claim_error = _first_schema_error(claim_schema, native)
    if claim_error:
        raise BaselineDataError(
            f"claim {native_id!r} failed schemas/scifact_claim_native.schema.json: {claim_error}"
        )
    cited = native["cited_doc_ids"]
    evidence = native["evidence"]
    cited_ids: list[int] = []
    for doc_id in cited:
        if not isinstance(doc_id, int):
            raise MissingEvidenceJoinError(
                f"{claim_ref} has non-integer cited doc id {doc_id!r}; D0 evidence join failed"
            )
        if doc_id in cited_ids:
            raise BaselineDataError(f"{claim_ref} repeats cited doc_id {doc_id}")
        cited_ids.append(doc_id)

    rationales_by_doc: dict[int, list[Rationale]] = {}
    for key, raw_rationales in evidence.items():
        try:
            doc_id = int(key)
        except (TypeError, ValueError) as exc:
            raise MissingEvidenceJoinError(
                f"{claim_ref} evidence key {key!r} is not a corpus doc id"
            ) from exc
        if str(doc_id) != str(key):
            raise MissingEvidenceJoinError(
                f"{claim_ref} evidence key {key!r} is not a corpus doc id"
            )
        if doc_id not in cited_ids:
            raise MissingEvidenceJoinError(
                f"{claim_ref} evidence doc_id {doc_id} is not in cited_doc_ids; D0 evidence join failed"
            )
        if not isinstance(raw_rationales, list):
            raise BaselineDataError(f"{claim_ref} doc {doc_id} rationales are not a list")
        parsed: list[Rationale] = []
        for raw in raw_rationales:
            try:
                rationale = Rationale.model_validate(raw)
            except ValidationError as exc:
                raise BaselineDataError(
                    f"{claim_ref} doc {doc_id} has a malformed native rationale"
                ) from exc
            parsed.append(rationale)
        rationales_by_doc[doc_id] = parsed

    bundle: list[GoldEvidenceDoc] = []
    for doc_id in cited_ids:
        try:
            doc = corpus[doc_id]
        except KeyError as exc:
            raise MissingEvidenceJoinError(
                f"{claim_ref} cited doc_id {doc_id} is not in the corpus; D0 evidence join failed. "
                "Empty annotated evidence is NEI-eligible only after cited documents join."
            ) from exc
        if doc.get("doc_id") != doc_id:
            raise BaselineDataError(
                f"corpus entry for {doc_id} has doc_id {doc.get('doc_id')!r}"
            )
        doc_error = _first_schema_error(doc_schema, doc)
        if doc_error:
            raise BaselineDataError(
                f"corpus doc {doc_id} failed schemas/scifact_corpus_doc.schema.json: {doc_error}"
            )
        abstract = doc["abstract"]
        for rationale in rationales_by_doc.get(doc_id, []):
            for index in rationale.sentences:
                if index >= len(abstract):
                    raise BaselineDataError(
                        f"{claim_ref} doc {doc_id} rationale sentence {index} is outside the abstract"
                    )
        bundle.append(
            GoldEvidenceDoc(
                doc_id=doc_id,
                title=doc["title"],
                abstract=list(abstract),
                structured=bool(doc["structured"]),
                rationales=rationales_by_doc.get(doc_id, []),
                snapshot_hash=snapshot_hash(doc),
            )
        )
    return PredictInput(
        claim_id=claim_ref,
        split_role=split_role,
        normalized_claim=native["claim"],
        gold_evidence_bundle=bundle,
        cited_doc_ids=cited_ids,
        native_label_space=NATIVE_LABEL_SPACE,
    )


def _assert_development_lock(root: Path, manifest: dict) -> None:
    if manifest.get("manifest_id") != "scifact_development_v1":
        raise BaselineDataError(
            f"development manifest id is {manifest.get('manifest_id')!r}"
        )
    if manifest.get("role") != "development":
        raise BaselineDataError(f"development manifest role is {manifest.get('role')!r}")
    if manifest.get("locked") is not True:
        raise BaselineDataError("scifact_development_v1 is not locked")
    digest = ids_sha256(manifest["ids"])
    if digest != manifest.get("ids_sha256"):
        raise BaselineDataError("development manifest ids_sha256 does not match its ids")
    locked = load_json(root / "data" / "pins" / "scifact" / "LOCKED.json")
    expected = locked.get("manifest_ids_sha256", {}).get("scifact_development_v1")
    if digest != expected:
        raise BaselineDataError(
            "development manifest ids_sha256 does not match data/pins/scifact/LOCKED.json"
        )


def load_development_inputs(
    root: Path,
    limit: int,
    corpus_config: str = "configs/corpus/scifact.yaml",
) -> LoadedInputs:
    """Load the first ``limit`` locked development claims in manifest order."""
    if limit < 1:
        raise BaselineDataError("limit must be at least 1")
    import yaml

    corpus_cfg = yaml.safe_load((root / corpus_config).read_text(encoding="utf-8"))
    manifest_rel = corpus_cfg["manifests"]["development"]
    manifest = load_manifest(root / manifest_rel)
    _assert_development_lock(root, manifest)
    if limit > len(manifest["ids"]):
        raise BaselineDataError(
            f"limit {limit} exceeds development manifest length {len(manifest['ids'])}"
        )
    raw_dir = root / corpus_cfg["raw_dir"]
    claims_path = raw_dir / manifest["source_file"]
    corpus_path = raw_dir / "corpus.jsonl"
    if not claims_path.is_file() or not corpus_path.is_file():
        raise BaselineDataError(
            "SciFact raw files are missing under data/raw/scifact/. "
            "Run python3 -m data.pins.scifact.download_verify. "
            "The baseline does not download or retrieve documents."
        )
    corpus_hash = sha256_file(corpus_path)
    if corpus_hash != corpus_cfg["corpus_hash"]:
        raise BaselineDataError(
            "corpus.jsonl sha256 does not match configs/corpus/scifact.yaml corpus_hash"
        )
    claims = index_claims(load_jsonl(claims_path), manifest["source_file"])
    corpus = load_corpus(raw_dir)
    claim_schema = _schema_validator(root, "scifact_claim_native.schema.json")
    doc_schema = _schema_validator(root, "scifact_corpus_doc.schema.json")
    selected: list[PredictInput] = []
    for native_id in manifest["ids"][:limit]:
        try:
            native = claims[native_id]
        except KeyError as exc:
            raise BaselineDataError(
                f"{manifest['manifest_id']} id {native_id} is missing from {manifest['source_file']}"
            ) from exc
        selected.append(
            build_predict_input(
                native,
                split_role="development",
                corpus=corpus,
                claim_schema=claim_schema,
                doc_schema=doc_schema,
            )
        )
    return LoadedInputs(
        split_role="development",
        inputs=selected,
        corpus_hash=corpus_hash,
        input_source="corpus_lock",
    )


def load_override_inputs(
    root: Path,
    *,
    claims_path: Path,
    corpus_path: Path,
    claim_ids: list[int],
    split_role: str,
) -> LoadedInputs:
    """Join an explicit claim file. Used to prove a missing-doc failure without editing data/."""
    if not claim_ids:
        raise BaselineDataError("override claim ids are empty")
    claims = index_claims(load_jsonl(claims_path), claims_path.name)
    corpus: dict[int, dict] = {}
    for record in load_jsonl(corpus_path):
        doc_id = record.get("doc_id")
        if not isinstance(doc_id, int):
            raise BaselineDataError(f"{corpus_path} has a document without an integer doc_id")
        if doc_id in corpus:
            raise BaselineDataError(f"{corpus_path} duplicates doc_id {doc_id}")
        corpus[doc_id] = record
    claim_schema = _schema_validator(root, "scifact_claim_native.schema.json")
    doc_schema = _schema_validator(root, "scifact_corpus_doc.schema.json")
    selected: list[PredictInput] = []
    for native_id in claim_ids:
        try:
            native = claims[native_id]
        except KeyError as exc:
            raise BaselineDataError(f"override claims are missing id {native_id}") from exc
        selected.append(
            build_predict_input(
                native,
                split_role=split_role,
                corpus=corpus,
                claim_schema=claim_schema,
                doc_schema=doc_schema,
            )
        )
    return LoadedInputs(
        split_role=split_role,
        inputs=selected,
        corpus_hash=sha256_file(corpus_path),
        input_source="override",
    )
