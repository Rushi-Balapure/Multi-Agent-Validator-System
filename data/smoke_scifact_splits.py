"""One-command check for the locked SciFact splits.

From the repository root:

    python3 -m data.smoke_scifact_splits

Downloads and verifies the release when ``data/raw/scifact/`` does not already
match the pin. Prints stable row counts, recomputes each manifest
``ids_sha256``, and schema-validates one claim plus evidence sample from
development, calibration, and held_out_local_eval. The official test sample
is checked as a claim shape and is not required to carry labels.

Requires ``pydantic``, ``jsonschema``, and ``pyyaml``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

EXPECTED_COUNTS = {
    "calibration": 100,
    "development": 709,
    "held_out_local_eval": 300,
    "official_test_unlabeled": 300,
    "corpus": 5183,
}
LOCKED_IDS_SHA256 = {
    "scifact_train_all": "ad7e39aa19e1b37cbcf11820b9ff3dfe5d674578c4fba92e3db220816d0b2a04",
    "scifact_calibration_v1": "6221cf17180dcad32e2655503d2138621701b8f3dfe32bd6afff4bcd9820b311",
    "scifact_development_v1": "d1a5b5a09e7a61b3216b1d816d4cf1ea85426dfa721d8f0561ba5dd3bd30c2dd",
    "scifact_held_out_dev_v1": "f454ba3f4706f9623699bdf722a170c1b97f28b74c325c927d428a2d81279b92",
    "scifact_official_test_v1": "b08b7a25df70a05fe97c7bbbdad2e218985431d1508159b9c9033867d9d991df",
}
FILE_SHA256 = {
    "claims_train.jsonl": (
        "f4c8fa82d8bd0653a9cc8d61a6ea48c25eacea64e90af5dbf390ebb1b74372f0",
        809,
    ),
    "claims_dev.jsonl": (
        "86f0435d08fdb65d1aa41d1472684f57e6e71930626497bdf4d7a9ec1a632217",
        300,
    ),
    "claims_test.jsonl": (
        "558930d75215c73f84a28fe538307d6d397c9de1ec7239514cf45f80d75d2ca3",
        300,
    ),
    "corpus.jsonl": (
        "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62",
        5183,
    ),
}
TARBALL_SHA256 = "11c621288d41ac144d29b13b0f8503b3820b7d6e8b1f6ff24dff335c196d76be"
UPSTREAM_COMMIT = "68b98a56d93e0f9da0d2aab4e6c3294699a0f72e"
CALIBRATION_SALT = "mavs-scifact-calibration-v1"
COUNT_ORDER = (
    "calibration",
    "development",
    "held_out_local_eval",
    "official_test_unlabeled",
    "corpus",
)
MANIFEST_ORDER = (
    "scifact_train_all",
    "scifact_calibration_v1",
    "scifact_development_v1",
    "scifact_held_out_dev_v1",
    "scifact_official_test_v1",
)


def fail(message: str) -> None:
    print(f"SMOKE FAIL: {message}")
    raise SystemExit(1)


def _load_schema(root: Path, name: str) -> dict:
    path = root / "schemas" / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _validator(schema: dict):
    from jsonschema import Draft202012Validator

    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _check_models_match_schemas(root: Path) -> None:
    from pydantic import ValidationError

    from validator.schemas import (
        Claim,
        Evidence,
        ExecutionStatus,
        Judgment,
        LabelSpace,
        ReportVerdict,
        Run,
        ScientificLabel,
    )

    pairs = {
        "mavs_claim_record.schema.json": Claim,
        "mavs_evidence_record.schema.json": Evidence,
        "mavs_label_record.schema.json": Judgment,
        "mavs_run_record.schema.json": Run,
        "mavs_report_verdict.schema.json": ReportVerdict,
    }
    for filename, model in pairs.items():
        schema = _load_schema(root, filename)
        properties = set(schema.get("properties", {}))
        required = set(schema.get("required", []))
        fields = set(model.model_fields)
        if not required <= fields:
            fail(f"{model.__name__} is missing required schema fields {sorted(required - fields)}")
        if not properties <= fields:
            fail(f"{model.__name__} is missing schema properties {sorted(properties - fields)}")
    label_schema = _load_schema(root, "mavs_evidence_label.schema.json")
    if set(label_schema["enum"]) != {item.value for item in ScientificLabel}:
        fail("ScientificLabel does not match mavs_evidence_label.schema.json")
    overlap = {item.value for item in ScientificLabel} & {item.value for item in ExecutionStatus}
    if overlap:
        fail(f"execution status overlaps scientific labels: {sorted(overlap)}")
    try:
        Judgment(
            claim_id="scifact:example",
            evidence_scope="native_scifact",
            label_space=LabelSpace.SCIFACT_NATIVE,
            label="timeout",
        )
    except ValidationError:
        pass
    else:
        fail("Judgment accepted timeout as a scientific label")
    try:
        Judgment(
            claim_id="scifact:example",
            evidence_scope="native_scifact",
            label_space=LabelSpace.SCIFACT_NATIVE,
            label="unaddressed",
        )
    except ValidationError:
        pass
    else:
        fail("Judgment accepted a four-way label as native SciFact gold")
    Judgment(
        claim_id="scifact:example",
        evidence_scope="native_scifact",
        label_space=LabelSpace.SCIFACT_NATIVE,
        label="SUPPORT",
        execution_status=ExecutionStatus.TIMEOUT,
        gold_provenance="upstream_scifact",
    )


def _validate_labeled_sample(bundle, corpus, schemas: dict) -> None:
    from data.scifact_loader import snapshot_hash

    native_errors = sorted(schemas["native_claim"].iter_errors(bundle.native_claim), key=str)
    if native_errors:
        fail(f"{bundle.split_role.value} native claim failed schema: {native_errors[0].message}")
    claim_payload = bundle.claim.model_dump(mode="json")
    claim_errors = sorted(schemas["claim"].iter_errors(claim_payload), key=str)
    if claim_errors:
        fail(f"{bundle.split_role.value} MAVS claim failed schema: {claim_errors[0].message}")
    if not bundle.gold_evidence or not bundle.same_evidence or not bundle.gold_labels:
        fail(f"{bundle.split_role.value} sample is missing gold or same-evidence")
    for evidence in (*bundle.same_evidence, *bundle.gold_evidence):
        payload = evidence.model_dump(mode="json")
        errors = sorted(schemas["evidence"].iter_errors(payload), key=str)
        if errors:
            fail(f"{bundle.split_role.value} evidence failed schema: {errors[0].message}")
        doc = corpus[evidence.doc_id]
        doc_errors = sorted(schemas["corpus_doc"].iter_errors(doc), key=str)
        if doc_errors:
            fail(f"corpus doc {evidence.doc_id} failed schema: {doc_errors[0].message}")
        if evidence.snapshot_hash != snapshot_hash(doc):
            fail(f"snapshot_hash mismatch for doc_id {evidence.doc_id}")
    for label in bundle.gold_labels:
        payload = label.model_dump(mode="json")
        errors = sorted(schemas["label"].iter_errors(payload), key=str)
        if errors:
            fail(f"{bundle.split_role.value} gold label failed schema: {errors[0].message}")
        if label.label not in {"SUPPORT", "CONTRADICT"}:
            fail("gold label was not native SUPPORT or CONTRADICT")
        if label.execution_status is not None:
            fail("upstream gold must not be stored as an execution status")


def _validate_test_sample(bundle, schemas: dict) -> None:
    native = bundle.native_claim
    if not isinstance(native.get("id"), int) or not isinstance(native.get("claim"), str) or not native["claim"]:
        fail("official test claim is missing id or claim text")
    if bundle.gold_labels or bundle.gold_evidence:
        fail("official test sample invented labels or gold evidence")
    payload = bundle.claim.model_dump(mode="json")
    errors = sorted(schemas["claim"].iter_errors(payload), key=str)
    if errors:
        fail(f"official test MAVS claim failed schema: {errors[0].message}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    src = root / "src"
    for entry in (str(root), str(src)):
        if entry not in sys.path:
            sys.path.insert(0, entry)

    try:
        import yaml
        from jsonschema import Draft202012Validator  # noqa: F401
    except ImportError as exc:
        fail(f"missing dependency ({exc}). Install pydantic, jsonschema, and pyyaml.")

    from data.pins.scifact.download_verify import (
        count_jsonl_records,
        ensure_scifact_raw,
        file_sha256,
        load_pin,
    )
    from data.scifact_loader import (
        MANIFESTS,
        SciFactDataError,
        ids_sha256,
        index_claims,
        load_corpus,
        load_json,
        load_jsonl,
        load_manifest,
        load_split,
    )

    _check_models_match_schemas(root)
    config_path = root / "configs" / "corpus" / "scifact.yaml"
    with config_path.open(encoding="utf-8") as handle:
        config = yaml.safe_load(handle)
    for key in ("pin", "lock", "manifests_dir", "raw_dir", "corpus_hash"):
        if key not in config:
            fail(f"configs/corpus/scifact.yaml is missing {key}")
    if config["corpus_hash"] not in {TARBALL_SHA256, FILE_SHA256["corpus.jsonl"][0]}:
        fail("configs/corpus/scifact.yaml corpus_hash is not the tarball or corpus.jsonl sha256")
    if config["corpus_hash"] != FILE_SHA256["corpus.jsonl"][0]:
        fail("configs/corpus/scifact.yaml corpus_hash must be the corpus.jsonl sha256 for this pin")
    if config.get("tarball_sha256") != TARBALL_SHA256:
        fail("configs/corpus/scifact.yaml tarball_sha256 does not match the pin")
    if config.get("upstream_git_commit") != UPSTREAM_COMMIT:
        fail("configs/corpus/scifact.yaml upstream commit does not match the pin")
    if config.get("calibration_salt") != CALIBRATION_SALT:
        fail("calibration salt does not match mavs-scifact-calibration-v1")

    pin = load_pin(root)
    if pin["source"]["tarball_sha256"] != TARBALL_SHA256:
        fail("PIN.json tarball_sha256 changed")
    if pin["source"]["upstream_git_commit"] != UPSTREAM_COMMIT:
        fail("PIN.json upstream commit changed")
    if pin["source"]["url"] != "https://scifact.s3-us-west-2.amazonaws.com/release/latest/data.tar.gz":
        fail("PIN.json data URL changed")
    if pin["split_policy"]["calibration_salt"] != CALIBRATION_SALT:
        fail("PIN.json calibration salt changed")
    if pin["split_policy"]["locked"] is not True:
        fail("PIN.json split policy is not locked")
    for name, (digest, count) in FILE_SHA256.items():
        meta = pin["files"][name]
        if meta["sha256"] != digest or meta["n_records"] != count:
            fail(f"PIN.json entry for {name} does not match the locked hash or count")

    try:
        ensure_scifact_raw(root)
    except Exception as exc:
        fail(f"download/verify failed: {exc}")

    raw_dir = root / config["raw_dir"]
    for name, (digest, count) in FILE_SHA256.items():
        path = raw_dir / name
        actual = file_sha256(path)
        actual_count = count_jsonl_records(path)
        if actual != digest or actual_count != count:
            fail(f"{name} sha256 or count mismatch: {actual} n={actual_count}")
        print(f"file_sha256 {name}={actual} n={actual_count}")

    lock = load_json(root / "data" / "pins" / "scifact" / "LOCKED.json")
    if lock.get("locked") is not True:
        fail("LOCKED.json is not locked")
    if lock.get("manifest_ids_sha256") != LOCKED_IDS_SHA256:
        fail("LOCKED.json manifest_ids_sha256 does not match the locked values")
    if lock.get("tarball_sha256") != TARBALL_SHA256:
        fail("LOCKED.json tarball_sha256 changed")

    manifests = {}
    for role, relative in MANIFESTS.items():
        path = root / relative
        manifest = load_manifest(path)
        manifest_id = manifest["manifest_id"]
        if manifest.get("locked") is not True:
            fail(f"{manifest_id} is not locked")
        if manifest.get("role") != role:
            fail(f"{manifest_id} role {manifest.get('role')!r} != {role!r}")
        recomputed = ids_sha256(manifest["ids"])
        expected = LOCKED_IDS_SHA256[manifest_id]
        if recomputed != expected or manifest.get("ids_sha256") != expected:
            fail(
                f"{manifest_id} ids_sha256 {recomputed} != locked {expected}"
            )
        if len(manifest["ids"]) != manifest["n_ids"] or len(set(manifest["ids"])) != manifest["n_ids"]:
            fail(f"{manifest_id} n_ids does not match the id list")
        source = raw_dir / manifest["source_file"]
        source_hash = file_sha256(source)
        if source_hash != manifest["source_sha256"] or source_hash != FILE_SHA256[manifest["source_file"]][0]:
            fail(f"{manifest_id} source_sha256 does not match {manifest['source_file']}")
        manifests[role] = manifest

    train_ids = manifests["source_train"]["ids"]
    calibration_ids = set(manifests["calibration"]["ids"])
    development_ids = set(manifests["development"]["ids"])
    if calibration_ids & development_ids:
        fail("calibration and development overlap")
    if calibration_ids | development_ids != set(train_ids):
        fail("calibration plus development is not the released training id set")
    if len(calibration_ids) != 100 or len(development_ids) != 709:
        fail("calibration or development count drifted")

    claims_by_file = {
        name: index_claims(load_jsonl(raw_dir / name), name)
        for name in ("claims_train.jsonl", "claims_dev.jsonl", "claims_test.jsonl")
    }
    for role, manifest in manifests.items():
        table = claims_by_file[manifest["source_file"]]
        missing = [claim_id for claim_id in manifest["ids"] if claim_id not in table]
        if missing:
            fail(f"{manifest['manifest_id']} has ids missing from {manifest['source_file']}")
        if role in {"source_train", "held_out_local_eval", "official_test_unlabeled"}:
            if set(manifest["ids"]) != set(table):
                fail(f"{manifest['manifest_id']} ids are not exactly {manifest['source_file']}")

    try:
        corpus = load_corpus(raw_dir)
    except SciFactDataError as exc:
        fail(str(exc))
    counts = {role: len(manifests[role]["ids"]) for role in EXPECTED_COUNTS if role != "corpus"}
    counts["corpus"] = len(corpus)
    for role in COUNT_ORDER:
        if counts[role] != EXPECTED_COUNTS[role]:
            fail(f"{role} count {counts[role]} != {EXPECTED_COUNTS[role]}")
        print(f"{role}={counts[role]}")
    for manifest_id in MANIFEST_ORDER:
        print(f"ids_sha256 {manifest_id}={LOCKED_IDS_SHA256[manifest_id]}")

    schemas = {
        "native_claim": _validator(_load_schema(root, "scifact_claim_native.schema.json")),
        "corpus_doc": _validator(_load_schema(root, "scifact_corpus_doc.schema.json")),
        "claim": _validator(_load_schema(root, "mavs_claim_record.schema.json")),
        "evidence": _validator(_load_schema(root, "mavs_evidence_record.schema.json")),
        "label": _validator(_load_schema(root, "mavs_label_record.schema.json")),
    }
    labeled_roles = ("development", "calibration", "held_out_local_eval")
    for role in labeled_roles:
        try:
            bundles = load_split(role, root)
        except SciFactDataError as exc:
            fail(str(exc))
        if len(bundles) != EXPECTED_COUNTS[role]:
            fail(f"{role} loader count {len(bundles)} != {EXPECTED_COUNTS[role]}")
        sample = next((bundle for bundle in bundles if bundle.gold_evidence), None)
        if sample is None:
            fail(f"{role} has no gold evidence sample")
        _validate_labeled_sample(sample, corpus, schemas)
        print(
            f"schema_ok {role} claim_id={sample.claim.claim_id} "
            f"same_evidence={len(sample.same_evidence)} gold_evidence={len(sample.gold_evidence)}"
        )

    try:
        test_bundles = load_split("official_test_unlabeled", root)
    except SciFactDataError as exc:
        fail(str(exc))
    if len(test_bundles) != EXPECTED_COUNTS["official_test_unlabeled"]:
        fail("official test loader count drifted")
    _validate_test_sample(test_bundles[0], schemas)
    print(
        f"schema_ok official_test_unlabeled claim_id={test_bundles[0].claim.claim_id} "
        "labels_not_required"
    )
    print("SMOKE OK")


if __name__ == "__main__":
    main()
