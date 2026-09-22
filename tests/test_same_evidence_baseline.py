"""Contract tests for the same-evidence B2 dry-run.

Verify from the repository root:

    python3 -m pip install -e ".[dev]"
    python3 -m data.pins.scifact.download_verify
    python3 -m pytest tests/test_same_evidence_baseline.py -q
    PYTHONPATH=src python3 -m validator.same_evidence.runner \\
        --config configs/baseline/same_evidence_b2.yaml \\
        --dry-run --limit 20 \\
        --output artifacts/same_evidence_b2/predictions.jsonl \\
        --run-sidecar artifacts/same_evidence_b2/run.json
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from validator.same_evidence.b2 import (
    LabelError,
    mock_compare_label,
    mock_reader_answer,
    normalize_label,
    reader_payload_for,
    run_b2,
)
from validator.same_evidence.b2 import MockClient
from data.scifact_loader import MANIFESTS, SciFactDataError, bundle_claim, snapshot_hash
from validator.same_evidence.inputs import (
    EXPECTED_CORPUS_HASH,
    EXPECTED_MANIFESTS,
    BaselineDataError,
    GoldEvidenceDoc,
    MissingEvidenceJoinError,
    PredictInput,
    Rationale,
    predict_input_from_bundle,
    repo_root,
    translate_loader_error,
)
from validator.same_evidence.runner import main
from validator.schemas import Run

ROOT = repo_root()
PREDICTION_LABELS = {"SUPPORT", "REFUTE", "NEI"}
FOUR_WAY = {"supported", "contradicted", "unaddressed", "underdetermined"}
DOC_HASH = "a" * 64


def _doc(doc_id: int = 10) -> dict:
    return {
        "doc_id": doc_id,
        "title": "Vitamin C trial",
        "abstract": ["Adults took vitamin C during one winter."],
        "structured": False,
    }


def _claim(claim_id: int, evidence: dict, cited: list[int]) -> dict:
    return {
        "id": claim_id,
        "claim": "Vitamin C shortens colds.",
        "evidence": evidence,
        "cited_doc_ids": cited,
    }


def _predict(rationales: list[Rationale]) -> PredictInput:
    return PredictInput(
        claim_id="scifact:1",
        split_role="development",
        normalized_claim="Vitamin C shortens colds.",
        gold_evidence_bundle=[
            GoldEvidenceDoc(
                doc_id=10,
                title="Vitamin C trial",
                abstract=["Adults took vitamin C during one winter."],
                structured=False,
                rationales=rationales,
                snapshot_hash=DOC_HASH,
            )
        ],
        cited_doc_ids=[10],
        native_label_space="scifact_SUPPORT_CONTRADICT",
    )


def _run_b2(item: PredictInput) -> dict:
    template = (ROOT / "prompts" / "same_evidence" / "b2_neutral_question_v1.txt").read_text(encoding="utf-8")
    reader = (ROOT / "prompts" / "same_evidence" / "b2_reader_v1.txt").read_text(encoding="utf-8")
    compare = (ROOT / "prompts" / "same_evidence" / "b2_compare_v1.txt").read_text(encoding="utf-8")
    return run_b2(
        item,
        seed=0,
        neutral_template=template,
        reader_prompt=reader,
        compare_prompt=compare,
        client=MockClient(0),
    )


def test_loader_manifest_paths_match_corpus_lock():
    assert MANIFESTS == EXPECTED_MANIFESTS
    assert EXPECTED_CORPUS_HASH == "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62"


def test_empty_evidence_joins_and_stays_nei_eligible():
    doc = _doc()
    bundle = bundle_claim(
        _claim(1, {}, [10]),
        split_role="development",
        corpus={10: doc},
        hashes={10: snapshot_hash(doc)},
    )
    assert bundle.gold_labels == []
    assert [item.doc_id for item in bundle.same_evidence] == [10]
    item = predict_input_from_bundle(bundle, {10: doc})
    assert item.nei_eligible() is True
    assert item.gold_evidence_bundle[0].rationales == []
    assert item.native_label_space == "scifact_SUPPORT_CONTRADICT"
    assert item.claim_id == "scifact:1"
    row = _run_b2(item)
    assert row["label"] in PREDICTION_LABELS
    assert row["rationale"]


def test_missing_cited_doc_is_a_join_failure_even_when_evidence_is_empty():
    with pytest.raises(SciFactDataError, match="not in corpus.jsonl"):
        bundle_claim(
            _claim(5, {}, [99]),
            split_role="development",
            corpus={10: _doc()},
            hashes={},
        )
    translated = translate_loader_error(
        SciFactDataError("claim 5 cites doc_id 99, which is not in corpus.jsonl")
    )
    assert isinstance(translated, MissingEvidenceJoinError)


def test_missing_evidence_object_is_not_treated_as_nei():
    doc = _doc()
    native = _claim(6, {}, [10])
    del native["evidence"]
    with pytest.raises(SciFactDataError, match="missing an evidence object"):
        bundle_claim(
            native,
            split_role="development",
            corpus={10: doc},
            hashes={10: snapshot_hash(doc)},
        )
    translated = translate_loader_error(SciFactDataError("claim 6 is missing an evidence object"))
    assert type(translated) is BaselineDataError
    assert "NEI-eligible" in str(translated)


def test_cli_missing_join_exits_nonzero(tmp_path: Path):
    predictions = tmp_path / "predictions.jsonl"
    sidecar = tmp_path / "run.json"
    code = f"""
from unittest.mock import patch
from data.scifact_loader import SciFactDataError
from validator.same_evidence.runner import main
err = SciFactDataError("claim 5 cites doc_id 99, which is not in corpus.jsonl")
with patch("validator.same_evidence.inputs.load_split", side_effect=err):
    main([
        "--dry-run", "--limit", "1",
        "--output", {str(predictions)!r},
        "--run-sidecar", {str(sidecar)!r},
    ])
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode != 0
    assert "EVIDENCE JOIN MISSING" in proc.stderr
    assert not predictions.exists()


def test_reader_payload_has_no_asserted_answer_or_rationales():
    item = _predict([Rationale(label="CONTRADICT", sentences=[0])])
    template = (ROOT / "prompts" / "same_evidence" / "b2_neutral_question_v1.txt").read_text(encoding="utf-8")
    payload = reader_payload_for(item, template, seed=0)
    assert set(payload) == {"neutral_question", "evidence"}
    assert item.normalized_claim in payload["neutral_question"]
    evidence_blob = json.dumps(payload["evidence"])
    assert item.normalized_claim not in evidence_blob
    assert "asserted_answer" not in json.dumps(payload)
    assert "CONTRADICT" not in evidence_blob
    for passage in payload["evidence"]:
        assert set(passage) == {"doc_id", "title", "abstract", "snapshot_hash"}
    reader_prompt = (ROOT / "prompts" / "same_evidence" / "b2_reader_v1.txt").read_text(encoding="utf-8")
    assert "asserted_answer" not in reader_prompt
    assert "SUPPORT" not in reader_prompt
    assert "REFUTE" not in reader_prompt


def test_mock_ignores_gold_rationales_and_matches_formula():
    empty = _run_b2(_predict([]))
    support = _run_b2(_predict([Rationale(label="SUPPORT", sentences=[0])]))
    contradict = _run_b2(_predict([Rationale(label="CONTRADICT", sentences=[0])]))
    assert empty["label"] == support["label"] == contradict["label"]
    assert empty["rationale"] == support["rationale"] == contradict["rationale"]
    question = empty["neutral_question"]
    doc_ids = empty["reader_cited_doc_ids"]
    answer = mock_reader_answer(0, question, doc_ids)
    expected = mock_compare_label(
        seed=0,
        claim_id="scifact:1",
        neutral_question=question,
        claim="Vitamin C shortens colds.",
        reader_answer=answer,
        doc_ids=doc_ids,
    )
    material = "\n".join(
        ["0", "scifact:1", question, "Vitamin C shortens colds.", answer, ",".join(str(d) for d in doc_ids)]
    )
    pinned = ("SUPPORT", "REFUTE", "NEI")[hashlib.sha256(material.encode("utf-8")).digest()[0] % 3]
    assert empty["label"] == expected == pinned
    again = _run_b2(_predict([]))
    assert again == empty


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("CONTRADICT", "REFUTE"), ("support", "SUPPORT"), (" nei ", "NEI"), ("REFUTE", "REFUTE")],
)
def test_native_label_mapping(raw: str, expected: str):
    assert normalize_label(raw) == expected


@pytest.mark.parametrize("raw", ["supported", "contradicted", "unaddressed", "underdetermined", "MAYBE"])
def test_four_way_labels_are_rejected(raw: str):
    with pytest.raises(LabelError):
        normalize_label(raw)


def test_dry_run_refuses_nonlocal_endpoint(tmp_path: Path):
    config = yaml.safe_load((ROOT / "configs" / "baseline" / "same_evidence_b2.yaml").read_text(encoding="utf-8"))
    config["base_url"] = "https://api.openai.com/v1"
    path = tmp_path / "cloud.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--config", str(path), "--dry-run", "--limit", "1"])
    assert exc.value.code != 0


def test_dry_run_twenty_development_claims_without_network(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    def fail_network(*_args, **_kwargs):
        raise AssertionError("dry-run opened a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)
    predictions = tmp_path / "predictions.jsonl"
    sidecar_path = tmp_path / "run.json"
    main(
        [
            "--config",
            "configs/baseline/same_evidence_b2.yaml",
            "--dry-run",
            "--limit",
            "20",
            "--output",
            str(predictions),
            "--run-sidecar",
            str(sidecar_path),
        ]
    )
    rows = [json.loads(line) for line in predictions.read_text(encoding="utf-8").splitlines() if line.strip()]
    manifest = json.loads((ROOT / "manifests" / "scifact" / "scifact_development_v1.json").read_text(encoding="utf-8"))
    assert [row["claim_id"] for row in rows] == [f"scifact:{claim_id}" for claim_id in manifest["ids"][:20]]
    assert len(rows) == 20
    for row in rows:
        assert {"claim_id", "label", "rationale"} <= set(row)
        assert row["label"] in PREDICTION_LABELS
        assert row["label"].lower() not in FOUR_WAY
        assert isinstance(row["rationale"], str) and row["rationale"].strip()
        assert row["system_id"] == "same_evidence_baseline"
        assert row["adaptation"] == "B2"
        assert row["inference_mode"] == "mock"
        blob = json.dumps(row)
        assert "asserted_answer" not in blob
        assert "CONTRADICT" not in blob
        assert "rationales" not in blob
    claims = {}
    wanted = set(manifest["ids"][:20])
    with (ROOT / "data" / "raw" / "scifact" / "claims_train.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            record = json.loads(line)
            if record["id"] in wanted:
                claims[record["id"]] = record
    assert claims[0]["evidence"] == {}
    assert any(row["claim_id"] == "scifact:0" for row in rows)

    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["system_id"] == "same_evidence_baseline"
    assert sidecar["inference_mode"] == "mock"
    assert sidecar["model_invoked"] is False
    assert sidecar["n_predictions"] == 20
    assert sidecar["n_nei_eligible_empty_evidence"] >= 1
    assert sidecar["input_source"] == "corpus_lock"
    Run.model_validate(sidecar["run"])
    schema = json.loads((ROOT / "schemas" / "mavs_run_record.schema.json").read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema).iter_errors(sidecar["run"]))
    assert errors == []
    assert sidecar["run"]["split"] == "development"
    assert sidecar["run"]["model_id"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert sidecar["run"]["status"] == "completed"
    assert sidecar["run"]["corpus_hash"] == EXPECTED_CORPUS_HASH
    config_bytes = (ROOT / "configs" / "baseline" / "same_evidence_b2.yaml").read_bytes()
    assert sidecar["run"]["config_hash"] == hashlib.sha256(config_bytes).hexdigest()
    prompt_texts = {
        name: (ROOT / "prompts" / "same_evidence" / filename).read_text(encoding="utf-8")
        for name, filename in (
            ("compare", "b2_compare_v1.txt"),
            ("neutral_question", "b2_neutral_question_v1.txt"),
            ("reader", "b2_reader_v1.txt"),
        )
    }
    chunks: list[str] = []
    for name in sorted(prompt_texts):
        chunks.append(name)
        chunks.append(prompt_texts[name])
    assert sidecar["run"]["prompt_hash"] == hashlib.sha256("\n".join(chunks).encode("utf-8")).hexdigest()
