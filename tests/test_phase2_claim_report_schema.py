"""Phase-2 Claim/Report schema fixtures and corpus-lock pin integrity."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from validator.schemas import Claim, ClaimSource, Report, SplitRole

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "phase2_claims"
SCHEMAS_DIR = REPO_ROOT / "schemas"

CLAIM_FIXTURES = (
    "numeric_claim.json",
    "negation_claim.json",
    "population_claim.json",
)

# Pin constants must match main / data.smoke_scifact_splits (do not edit lock files).
LOCKED_IDS_SHA256 = {
    "scifact_train_all": "ad7e39aa19e1b37cbcf11820b9ff3dfe5d674578c4fba92e3db220816d0b2a04",
    "scifact_calibration_v1": "6221cf17180dcad32e2655503d2138621701b8f3dfe32bd6afff4bcd9820b311",
    "scifact_development_v1": "d1a5b5a09e7a61b3216b1d816d4cf1ea85426dfa721d8f0561ba5dd3bd30c2dd",
    "scifact_held_out_dev_v1": "f454ba3f4706f9623699bdf722a170c1b97f28b74c325c927d428a2d81279b92",
    "scifact_official_test_v1": "b08b7a25df70a05fe97c7bbbdad2e218985431d1508159b9c9033867d9d991df",
}
LOCKED_FILE_SHA256 = "15d2229757e207a1fd2eb03c7e48a45c423771ecef0fcdb0cfbb32a61c950cf3"
PIN_FILE_SHA256 = "ee7edae13e7c764fa998f9b28642e0c784a782ca57451c52ca00a80532d47832"
MANIFEST_FILE_SHA256 = {
    "scifact_calibration_v1.json": "d2cc7303d7e963abfabd564aed90a0fe87a4a86a885bf5b3b8128ee10cf3878b",
    "scifact_development_v1.json": "bfca477c29c6115472498d6ceb9aec24a041f393a5a345db636e369d432fa451",
    "scifact_held_out_dev_v1.json": "50510a56cab213f33b8dff70735ff4e34425c47e1b605d0fa4b10a4f79cb7efc",
    "scifact_official_test_v1.json": "a815312b35ee820474ad0c60ad958f5dca676bf6ae9c8a0f8617ffbfcbcc067e",
    "scifact_train_all.json": "0535d76e75cce9ef7c06586b698bdc97d480a18486bb598d065f3737c0b0ce13",
}
TARBALL_SHA256 = "11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _schema_validator(name: str) -> Draft202012Validator:
    schema = _load_json(SCHEMAS_DIR / name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.fixture(scope="module")
def claim_schema() -> Draft202012Validator:
    return _schema_validator("mavs_claim_record.schema.json")


@pytest.fixture(scope="module")
def report_schema() -> Draft202012Validator:
    return _schema_validator("mavs_report_record.schema.json")


@pytest.mark.parametrize("filename", CLAIM_FIXTURES)
def test_phase2_claim_fixtures_validate(filename: str, claim_schema: Draft202012Validator) -> None:
    payload = _load_json(FIXTURE_DIR / filename)
    claim_schema.validate(payload)
    claim = Claim.model_validate(payload)
    assert claim.source.dataset == "agentic"
    assert claim.exact_source_span
    assert claim.neutral_question
    assert claim.asserted_answer
    assert claim.subject and claim.relation and claim.object


def test_numeric_fixture_has_units_and_magnitude(claim_schema: Draft202012Validator) -> None:
    payload = _load_json(FIXTURE_DIR / "numeric_claim.json")
    claim_schema.validate(payload)
    claim = Claim.model_validate(payload)
    assert claim.units == "mmHg"
    assert claim.time == "12 weeks"
    assert claim.comparator == "placebo"
    assert claim.modality == "magnitude"
    assert "12" in (claim.asserted_answer or "")


def test_negation_fixture_marks_negation(claim_schema: Draft202012Validator) -> None:
    payload = _load_json(FIXTURE_DIR / "negation_claim.json")
    claim_schema.validate(payload)
    claim = Claim.model_validate(payload)
    assert claim.modality == "negation"
    assert "not" in (claim.relation or "").lower() or "not" in claim.normalized_claim.lower()


def test_population_fixture_has_population_qualifier(claim_schema: Draft202012Validator) -> None:
    payload = _load_json(FIXTURE_DIR / "population_claim.json")
    claim_schema.validate(payload)
    claim = Claim.model_validate(payload)
    assert claim.population
    assert "65" in claim.population


def test_frozen_report_fixture_validates(
    claim_schema: Draft202012Validator,
    report_schema: Draft202012Validator,
) -> None:
    payload = _load_json(FIXTURE_DIR / "frozen_report.json")
    report_schema.validate(payload)
    report = Report.model_validate(payload)
    assert report.frozen_conclusion
    assert set(report.claim_ids) == {
        "agentic:phase2-numeric-v1",
        "agentic:phase2-negation-v1",
        "agentic:phase2-population-v1",
    }
    assert len(report.claims) == 3
    for embedded in report.claims:
        claim_schema.validate(embedded.model_dump(mode="json"))
        assert embedded.report_id == report.report_id


def test_claim_source_scifact_still_requires_native_id() -> None:
    with pytest.raises(ValidationError):
        ClaimSource(dataset="scifact", native_id=None)
    source = ClaimSource(dataset="scifact", native_id=42, split_role=SplitRole.DEVELOPMENT)
    assert source.dataset == "scifact"
    assert source.native_id == 42


def test_claim_source_agentic_allows_null_native_id(claim_schema: Draft202012Validator) -> None:
    payload = {
        "claim_id": "agentic:tmp",
        "normalized_claim": "Example agentic claim.",
        "source": {"dataset": "agentic", "native_id": None, "split_role": None},
    }
    claim_schema.validate(payload)
    claim = Claim.model_validate(payload)
    assert claim.source.native_id is None


def test_report_requires_claim_ids_or_claims(report_schema: Draft202012Validator) -> None:
    empty = {
        "report_id": "agentic:empty",
        "frozen_conclusion": "No claims listed.",
        "claim_ids": [],
        "claims": [],
    }
    with pytest.raises(ValidationError):
        Report.model_validate(empty)
    errors = list(report_schema.iter_errors(empty))
    assert errors


def test_locked_pin_and_manifest_hashes_unchanged() -> None:
    locked_path = REPO_ROOT / "data" / "pins" / "scifact" / "LOCKED.json"
    pin_path = REPO_ROOT / "data" / "pins" / "scifact" / "PIN.json"
    assert _file_sha256(locked_path) == LOCKED_FILE_SHA256
    assert _file_sha256(pin_path) == PIN_FILE_SHA256

    locked = _load_json(locked_path)
    pin = _load_json(pin_path)
    assert locked.get("locked") is True
    assert locked.get("manifest_ids_sha256") == LOCKED_IDS_SHA256
    assert locked.get("tarball_sha256") == TARBALL_SHA256
    assert pin["source"]["tarball_sha256"] == TARBALL_SHA256
    assert pin["split_policy"]["locked"] is True

    manifests_dir = REPO_ROOT / "manifests" / "scifact"
    for name, digest in MANIFEST_FILE_SHA256.items():
        path = manifests_dir / name
        assert _file_sha256(path) == digest
        manifest = _load_json(path)
        manifest_id = manifest["manifest_id"]
        assert manifest.get("ids_sha256") == LOCKED_IDS_SHA256[manifest_id]
        assert manifest.get("locked") is True


def test_pydantic_report_fields_match_json_schema() -> None:
    schema = _load_json(SCHEMAS_DIR / "mavs_report_record.schema.json")
    properties = set(schema.get("properties", {}))
    required = set(schema.get("required", []))
    fields = set(Report.model_fields)
    assert required <= fields
    assert properties <= fields
