"""Frozen claim-id sample files and seeded draws."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from data.scifact_loader import ids_sha256
from validator.claim_sample import (
    ClaimSampleError,
    build_claim_sample,
    claim_ids_from_file,
    dump_claim_sample,
    load_claim_sample,
    parse_claim_ids_csv,
    sample_from_manifest,
    sample_native_ids,
)
from validator.same_evidence._repo import find_repo_root

ROOT = find_repo_root()
DEV_MANIFEST = ROOT / "manifests" / "scifact" / "scifact_development_v1.json"


def test_seeded_sample_is_reproducible_and_not_a_prefix():
    universe = list(range(20))
    first = sample_native_ids(universe, n=5, seed=42)
    second = sample_native_ids(universe, n=5, seed=42)
    other = sample_native_ids(universe, n=5, seed=7)
    assert first == second
    assert first != other
    assert first != universe[:5]
    assert len(set(first)) == 5


def test_sample_refuses_overdraw_and_duplicates():
    with pytest.raises(ClaimSampleError, match="cannot sample"):
        sample_native_ids([1, 2], n=3, seed=0)
    with pytest.raises(ClaimSampleError, match="duplicate"):
        sample_native_ids([1, 1, 2], n=2, seed=0)


def test_build_and_roundtrip_sample_file(tmp_path: Path):
    sample = build_claim_sample(
        sample_id="dev5_seed0",
        split_role="development",
        seed=0,
        native_ids=[9, 2, 4],
        source_manifest="manifests/scifact/scifact_development_v1.json",
        label_distribution={"SUPPORT": 1, "CONTRADICT": 1, "NEI": 1},
    )
    assert sample.claim_ids == ["scifact:9", "scifact:2", "scifact:4"]
    assert sample.ids_sha256 == ids_sha256([9, 2, 4])
    path = tmp_path / "sample.json"
    dump_claim_sample(sample, path)
    loaded = load_claim_sample(path)
    assert loaded.claim_ids == sample.claim_ids
    assert claim_ids_from_file(path, limit=2) == ["scifact:9", "scifact:2"]


def test_sample_detects_hash_and_order_drift(tmp_path: Path):
    sample = build_claim_sample(
        sample_id="x",
        split_role="development",
        seed=1,
        native_ids=[0, 2],
        source_manifest="manifests/scifact/scifact_development_v1.json",
    )
    payload = sample.model_dump(mode="json")
    payload["ids_sha256"] = "0" * 64
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ClaimSampleError, match="ids_sha256"):
        load_claim_sample(bad)


def test_label_distribution_must_sum_to_n():
    with pytest.raises(ValueError, match="sum"):
        build_claim_sample(
            sample_id="x",
            split_role="development",
            seed=1,
            native_ids=[0, 2],
            source_manifest="m.json",
            label_distribution={"SUPPORT": 2, "CONTRADICT": 0, "NEI": 1},
        )


def test_parse_claim_ids_csv():
    assert parse_claim_ids_csv("scifact:0, scifact:2") == ["scifact:0", "scifact:2"]
    with pytest.raises(ClaimSampleError, match="empty"):
        parse_claim_ids_csv("scifact:0,")
    with pytest.raises(ClaimSampleError, match="duplicate"):
        parse_claim_ids_csv("scifact:0,scifact:0")


def test_committed_dev300_sample_is_locked_and_not_a_prefix():
    path = ROOT / "data" / "manifests" / "dev300_seed42.json"
    sample = load_claim_sample(path)
    assert sample.n_ids == 300
    assert sample.seed == 42
    assert sample.split_role == "development"
    assert sample.label_distribution is not None
    assert sum(sample.label_distribution.values()) == 300
    manifest = json.loads(DEV_MANIFEST.read_text(encoding="utf-8"))
    prefix = [f"scifact:{native_id}" for native_id in manifest["ids"][:300]]
    assert sample.claim_ids != prefix
    assert set(sample.native_ids) <= set(manifest["ids"])


def test_sample_from_locked_development_manifest():
    sample = sample_from_manifest(
        DEV_MANIFEST,
        sample_id="dev300_seed42",
        split_role="development",
        n=300,
        seed=42,
    )
    assert sample.n_ids == 300
    assert len(sample.claim_ids) == 300
    assert sample.claim_ids[0].startswith("scifact:")
    manifest = json.loads(DEV_MANIFEST.read_text(encoding="utf-8"))
    prefix = [f"scifact:{native_id}" for native_id in manifest["ids"][:300]]
    assert sample.claim_ids != prefix
    assert set(sample.native_ids) <= set(manifest["ids"])
