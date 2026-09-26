"""Frozen claim-id samples shared by B2, V, and later baselines.

A sample file is a JSON object with a seeded list of project claim ids
(``scifact:{native_id}``). B2 and V both read the same file so they judge
the same claims in the same order. The first-N prefix of a split manifest
is not a sample.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from validator.retrieve import native_id_from_claim_id, project_claim_id
from validator.retrieval.errors import RetrievalError
from validator.same_evidence._repo import ensure_repo_on_path

ensure_repo_on_path()

from data.scifact_loader import ids_sha256, load_manifest  # noqa: E402

_SHA256 = r"^[a-f0-9]{64}$"
ALLOWED_SPLITS = (
    "development",
    "calibration",
    "held_out_local_eval",
    "official_test_unlabeled",
)


class ClaimSampleError(ValueError):
    """A claim-id sample file is missing, malformed, or inconsistent."""


class ClaimSample(BaseModel):
    """One frozen id list plus the hashes that lock it."""

    model_config = ConfigDict(extra="forbid")

    sample_id: str = Field(min_length=1)
    split_role: str = Field(min_length=1)
    seed: int
    n_ids: int = Field(ge=1)
    ids_sha256: str = Field(pattern=_SHA256)
    claim_ids: list[str] = Field(min_length=1)
    native_ids: list[int] = Field(min_length=1)
    source_manifest: str = Field(min_length=1)
    label_distribution: dict[str, int] | None = None

    @field_validator("split_role")
    @classmethod
    def split_is_known(cls, value: str) -> str:
        if value not in ALLOWED_SPLITS:
            raise ValueError(f"split_role {value!r} is not one of {ALLOWED_SPLITS}")
        return value

    @model_validator(mode="after")
    def lists_agree(self) -> ClaimSample:
        if self.n_ids != len(self.claim_ids) or self.n_ids != len(self.native_ids):
            raise ValueError(
                f"n_ids {self.n_ids} does not match claim_ids ({len(self.claim_ids)}) "
                f"or native_ids ({len(self.native_ids)})"
            )
        if len(self.claim_ids) != len(set(self.claim_ids)):
            raise ValueError("claim_ids contains duplicates")
        if len(self.native_ids) != len(set(self.native_ids)):
            raise ValueError("native_ids contains duplicates")
        derived = [project_claim_id(native_id) for native_id in self.native_ids]
        if derived != self.claim_ids:
            raise ValueError("claim_ids must be scifact:{native_id} in native_ids order")
        digest = ids_sha256(self.native_ids)
        if digest != self.ids_sha256:
            raise ValueError(
                f"ids_sha256 {self.ids_sha256} does not match native_ids ({digest})"
            )
        if self.label_distribution is not None:
            allowed = {"SUPPORT", "CONTRADICT", "NEI"}
            unknown = set(self.label_distribution) - allowed
            if unknown:
                raise ValueError(f"label_distribution has unknown keys {sorted(unknown)}")
            if any(
                isinstance(count, bool) or not isinstance(count, int) or count < 0
                for count in self.label_distribution.values()
            ):
                raise ValueError("label_distribution counts must be non-negative integers")
            if sum(self.label_distribution.values()) != self.n_ids:
                raise ValueError("label_distribution counts must sum to n_ids")
        return self


def load_claim_sample(path: Path) -> ClaimSample:
    """Load and validate a frozen claim-id sample file."""
    if not path.is_file():
        raise ClaimSampleError(f"claim-ids file is missing: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ClaimSampleError(f"{path} is not JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise ClaimSampleError(f"{path} must be a JSON object")
    try:
        return ClaimSample.model_validate(raw)
    except Exception as exc:
        raise ClaimSampleError(f"{path} is not a valid claim sample: {exc}") from exc


def claim_ids_from_file(path: Path, *, limit: int | None = None) -> list[str]:
    """Return project claim ids from a sample file, optionally capped."""
    if limit is not None and (isinstance(limit, bool) or not isinstance(limit, int) or limit < 1):
        raise ClaimSampleError("limit must be a positive integer")
    sample = load_claim_sample(path)
    selected = list(sample.claim_ids)
    if limit is not None:
        selected = selected[:limit]
    return selected


def sample_native_ids(universe: list[int], *, n: int, seed: int) -> list[int]:
    """Seeded sample without replacement. Order is the draw order, not sorted."""
    if n < 1:
        raise ClaimSampleError("n must be at least 1")
    if n > len(universe):
        raise ClaimSampleError(f"cannot sample {n} ids from a universe of {len(universe)}")
    if len(universe) != len(set(universe)):
        raise ClaimSampleError("universe contains duplicate native ids")
    rng = random.Random(seed)
    return rng.sample(list(universe), n)


def build_claim_sample(
    *,
    sample_id: str,
    split_role: str,
    seed: int,
    native_ids: list[int],
    source_manifest: str,
    label_distribution: Mapping[str, int] | None = None,
) -> ClaimSample:
    """Build a locked sample from already-chosen native ids."""
    claim_ids = [project_claim_id(native_id) for native_id in native_ids]
    return ClaimSample(
        sample_id=sample_id,
        split_role=split_role,
        seed=seed,
        n_ids=len(native_ids),
        ids_sha256=ids_sha256(native_ids),
        claim_ids=claim_ids,
        native_ids=list(native_ids),
        source_manifest=source_manifest,
        label_distribution=dict(label_distribution) if label_distribution is not None else None,
    )


def sample_from_manifest(
    manifest_path: Path,
    *,
    sample_id: str,
    split_role: str,
    n: int,
    seed: int,
    label_distribution: Mapping[str, int] | None = None,
) -> ClaimSample:
    """Draw a seeded sample from a locked SciFact manifest of native ids."""
    try:
        manifest = load_manifest(manifest_path)
    except Exception as exc:
        raise ClaimSampleError(f"cannot load manifest {manifest_path}: {exc}") from exc
    native_ids = sample_native_ids(list(manifest["ids"]), n=n, seed=seed)
    source = str(manifest_path)
    return build_claim_sample(
        sample_id=sample_id,
        split_role=split_role,
        seed=seed,
        native_ids=native_ids,
        source_manifest=source,
        label_distribution=label_distribution,
    )


def dump_claim_sample(sample: ClaimSample, path: Path) -> None:
    """Write a sample JSON file with a trailing newline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(sample.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def parse_claim_ids_csv(value: str) -> list[str]:
    """Split a comma-separated project-id list. Empty tokens are refused."""
    if not isinstance(value, str) or not value.strip():
        raise ClaimSampleError("--claim-ids was empty")
    parts = [part.strip() for part in value.split(",")]
    if any(part == "" for part in parts):
        raise ClaimSampleError(f"--claim-ids has an empty id: {value!r}")
    seen: set[str] = set()
    for claim_id in parts:
        try:
            native_id_from_claim_id(claim_id)
        except RetrievalError as exc:
            raise ClaimSampleError(str(exc)) from exc
        if claim_id in seen:
            raise ClaimSampleError(f"duplicate claim id {claim_id}")
        seen.add(claim_id)
    return parts


def as_public_dict(sample: ClaimSample) -> dict[str, Any]:
    return sample.model_dump(mode="json")
