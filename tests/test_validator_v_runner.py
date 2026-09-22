"""Offline Stack V batch runner: fixture reports, label mapping, and the gather hook."""

from __future__ import annotations

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

from evaluation.harness import compare_false_endorsement
from evaluation.score_predictions import score_prediction_rows
from validator.fixture_pipeline import load_report_fixture
from validator.live_judgment import load_live_settings
from validator.retrieval.config import load_retrieval_config
from validator.same_evidence._repo import find_repo_root
from validator.schemas import Run, ScientificLabel
from validator.validator_v.labels import FOUR_WAY_TO_NATIVE, map_four_way_label
from validator.validator_v.runner import (
    DEVELOPMENT_CLAIM_BUDGET,
    PHASE3_B2_CLAIM_IDS,
    execute,
    main,
    parse_args,
)

ROOT = find_repo_root()
CONFIG = ROOT / "configs" / "validator_v" / "development.yaml"
HAPPY = ROOT / "tests" / "fixtures" / "judgment" / "e2e_happy.json"
CONFLICT = ROOT / "tests" / "fixtures" / "judgment" / "e2e_conflict.json"
NATIVE = {"SUPPORT", "REFUTE", "NEI"}
FOUR_WAY = {item.value for item in ScientificLabel}
LEAK = "LEAK_ASSERTED_ANSWER"


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args, **_kwargs):
        raise AssertionError("validator V dry-run opened a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_four_way_mapping_covers_the_eval_label_space():
    assert map_four_way_label("supported") == "SUPPORT"
    assert map_four_way_label("contradicted") == "REFUTE"
    assert map_four_way_label("unaddressed") == "NEI"
    assert map_four_way_label("underdetermined") == "NEI"
    assert set(FOUR_WAY_TO_NATIVE) == FOUR_WAY
    assert set(FOUR_WAY_TO_NATIVE.values()) <= NATIVE
    with pytest.raises(ValueError):
        map_four_way_label("SUPPORT")


def test_dry_run_writes_predictions_and_run_sidecar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    predictions = tmp_path / "predictions.jsonl"
    sidecar_path = tmp_path / "run.json"
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--dry-run",
                "--output",
                str(predictions),
                "--run-sidecar",
                str(sidecar_path),
            ]
        )
        == 0
    )
    rows = _rows(predictions)
    assert len(rows) == 3
    assert len(rows) <= DEVELOPMENT_CLAIM_BUDGET
    by_id = {row["claim_id"]: row for row in rows}
    assert set(by_id) == {"scifact:900042", "scifact:900142", "scifact:900242"}
    happy = by_id["scifact:900042"]
    assert happy["label"] == "SUPPORT"
    assert happy["label_4way"] == "supported"
    assert happy["d0_label_4way"] == "supported"
    assert happy["d1_label_4way"] == "supported"
    assert happy["execution_status"] == "ok"
    assert happy["proposer_claim_id"] == "agentic:e2e-happy:1"
    conflict = by_id["scifact:900142"]
    assert conflict["label"] == "NEI"
    assert conflict["label_4way"] == "underdetermined"
    assert conflict["d0_label_4way"] == "supported"
    assert conflict["d1_label_4way"] == "contradicted"
    assert conflict["execution_status"] == "ok"
    missing = by_id["scifact:900242"]
    assert missing["label"] == "NEI"
    assert missing["label_4way"] == "underdetermined"
    assert missing["d0_label_4way"] == "unaddressed"
    assert missing["execution_status"] == "failed"
    blob = predictions.read_text(encoding="utf-8") + sidecar_path.read_text(encoding="utf-8")
    assert LEAK not in blob
    assert "asserted_answer" not in blob
    for row in rows:
        assert row["method_id"] == "V"
        assert row["adaptation"] == "V"
        assert row["inference_mode"] == "mock"
        assert row["evidence_scope"] == "D0_union_D1"
        assert row["label"] in NATIVE
        assert row["label_4way"] in FOUR_WAY
        assert row["system_id"] == "validator_v"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["method_id"] == "V"
    assert sidecar["adaptation"] == "V"
    assert sidecar["inference_mode"] == "mock"
    assert sidecar["model_invoked"] is False
    assert sidecar["n_predictions"] == 3
    assert sidecar["development_claim_budget"] == 20
    assert sidecar["input_source"] == "fixture_report"
    assert sidecar["label_mapping"] == {
        "supported": "SUPPORT",
        "contradicted": "REFUTE",
        "unaddressed": "NEI",
        "underdetermined": "NEI",
    }
    run = sidecar["run"]
    assert run["run_id"].startswith("validator-v-development-s0-n3-")
    assert run["split"] == "development"
    assert run["seed"] == 0
    assert run["model_id"] == "qwen2.5-coder-1.5b-instruct"
    assert len(run["prompt_hash"]) == 64
    assert len(run["corpus_hash"]) == 64
    assert len(run["config_hash"]) == 64
    assert run["status"] == "completed"
    schema = json.loads((ROOT / "schemas" / "mavs_run_record.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(run)) == []
    Run.model_validate(run)
    scored = []
    for row in rows:
        if row["execution_status"] != "ok":
            continue
        copied = dict(row)
        copied["label_gold"] = "SUPPORT" if row["label"] == "SUPPORT" else "REFUTE"
        scored.append(copied)
    report = score_prediction_rows(scored, run_id=run["run_id"])
    assert report["method_id"] == "V"
    assert report["n_scored"] == 2
    assert report["inference_mode"] == "mock"
    b2_rows = [
        {
            "claim_id": row["claim_id"],
            "label": row["label_gold"],
            "label_gold": row["label_gold"],
            "method_id": "B2",
            "adaptation": "B2",
            "inference_mode": "mock",
            "execution_status": "ok",
        }
        for row in scored
    ]
    comparison = compare_false_endorsement(
        b2_predictions=b2_rows,
        v_predictions=scored,
        b2_run_id="fixture-b2",
        v_run_id=run["run_id"],
    )
    assert comparison.v.method_id == "V"
    assert comparison.v.status == "scored"
    assert comparison.claim_ids == tuple(sorted(row["claim_id"] for row in scored))


def test_limit_keeps_a_fixture_subset_and_rejects_more_than_twenty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _block_network(monkeypatch)
    predictions = tmp_path / "predictions.jsonl"
    sidecar = tmp_path / "run.json"
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--dry-run",
                "--limit",
                "2",
                "--output",
                str(predictions),
                "--run-sidecar",
                str(sidecar),
            ]
        )
        == 0
    )
    rows = _rows(predictions)
    assert [row["claim_id"] for row in rows] == ["scifact:900042", "scifact:900142"]
    assert json.loads(sidecar.read_text(encoding="utf-8"))["n_predictions"] == 2
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--dry-run",
                "--limit",
                "21",
                "--output",
                str(tmp_path / "over.jsonl"),
                "--run-sidecar",
                str(tmp_path / "over-run.json"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "over.jsonl").exists()
    assert main(["--config", str(CONFIG), "--dry-run", "--limit", "0"]) == 2
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--dry-run",
                "--gather",
                "--limit",
                "1",
                "--output",
                str(tmp_path / "mix.jsonl"),
                "--run-sidecar",
                str(tmp_path / "mix.json"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "mix.jsonl").exists()


def test_cli_module_writes_the_artifact_paths(tmp_path: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    predictions = tmp_path / "predictions.jsonl"
    sidecar = tmp_path / "run.json"
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "validator.validator_v",
            "--config",
            "configs/validator_v/development.yaml",
            "--dry-run",
            "--output",
            str(predictions),
            "--run-sidecar",
            str(sidecar),
        ],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "method_id=V" in proc.stdout
    assert "inference_mode=mock" in proc.stdout
    sidecar_payload = json.loads(sidecar.read_text(encoding="utf-8"))
    assert sidecar_payload["method_id"] == "V"
    assert sidecar_payload["n_predictions"] == len(_rows(predictions))


def test_gather_passes_the_neutral_question_and_not_gold_d0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _block_network(monkeypatch)
    import validator.retrieve as retrieve_mod
    import validator.validator_v.runner as batch

    happy = load_report_fixture(HAPPY)
    template_bundle = happy.attachments[0].d1_bundle
    assert template_bundle is not None
    claim_text = "In the mouse model, compound MX-42 increased memory retention."
    seen: list[tuple[str, str]] = []

    def fake_gather(claim_or_neutral_question, config, claim_id):
        assert isinstance(claim_or_neutral_question, str)
        assert LEAK not in claim_or_neutral_question
        assert "asserted_answer" not in claim_or_neutral_question
        seen.append((claim_or_neutral_question, claim_id))
        return template_bundle.model_copy(update={"claim_id": claim_id})

    def fake_texts(claim_ids, _path):
        return {claim_id: claim_text for claim_id in claim_ids}

    monkeypatch.setattr(retrieve_mod, "gather", fake_gather)
    monkeypatch.setattr(retrieve_mod, "load_claim_texts", fake_texts)
    d0_seen: list[list] = []
    real_run = batch.run_fixture

    def spy_run(fixture, **kwargs):
        d0_seen.append(list(fixture.d0_evidence))
        assert fixture.claim.asserted_answer is None
        assert kwargs.get("live") is None
        return real_run(fixture, **kwargs)

    monkeypatch.setattr(batch, "run_fixture", spy_run)
    predictions = tmp_path / "predictions.jsonl"
    sidecar_path = tmp_path / "run.json"
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--gather",
                "--limit",
                "1",
                "--output",
                str(predictions),
                "--run-sidecar",
                str(sidecar_path),
            ]
        )
        == 0
    )
    expected_id = PHASE3_B2_CLAIM_IDS[0]
    expected_question = (
        (ROOT / "prompts" / "validator_v" / "neutral_question_v1.txt")
        .read_text(encoding="utf-8")
        .replace("{claim}", claim_text)
        .strip()
    )
    assert seen == [(expected_question, expected_id)]
    assert d0_seen == [[]]
    row = _rows(predictions)[0]
    assert row["claim_id"] == expected_id
    assert row["method_id"] == "V"
    assert row["inference_mode"] == "mock"
    assert row["d1_label_4way"] == "supported"
    assert row["label_4way"] == "underdetermined"
    assert row["label"] == "NEI"
    assert row["execution_status"] == "failed"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["input_source"] == "gather"
    assert sidecar["n_predictions"] == 1
    assert sidecar["development_claim_budget"] == 20
    assert sidecar["claim_ids"] == [expected_id]
    assert sidecar["run"]["run_id"].startswith("validator-v-gather-development-s0-n1-")
    assert sidecar["run"]["run_id"] != "validator-v-development-s0-n3-d5cecb97c55b"


def test_gather_preserves_phase3_b2_claim_id_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    """Mocked gather over the 20 B2 ids writes predictions/run.json with method_id=V."""
    _block_network(monkeypatch)
    import validator.retrieve as retrieve_mod
    import validator.validator_v.runner as batch

    happy = load_report_fixture(HAPPY)
    template_bundle = happy.attachments[0].d1_bundle
    assert template_bundle is not None
    gather_order: list[str] = []

    def fake_gather(claim_or_neutral_question, config, claim_id):
        assert isinstance(claim_or_neutral_question, str)
        gather_order.append(claim_id)
        return template_bundle.model_copy(update={"claim_id": claim_id})

    def fake_texts(claim_ids, _path):
        assert list(claim_ids) == list(PHASE3_B2_CLAIM_IDS)
        return {claim_id: f"claim text for {claim_id}" for claim_id in claim_ids}

    monkeypatch.setattr(retrieve_mod, "gather", fake_gather)
    monkeypatch.setattr(retrieve_mod, "load_claim_texts", fake_texts)
    predictions = tmp_path / "predictions.jsonl"
    sidecar_path = tmp_path / "run.json"
    claim_ids_arg = ",".join(PHASE3_B2_CLAIM_IDS)
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--gather",
                "--claim-ids",
                claim_ids_arg,
                "--limit",
                "20",
                "--output",
                str(predictions),
                "--run-sidecar",
                str(sidecar_path),
            ]
        )
        == 0
    )
    rows = _rows(predictions)
    assert [row["claim_id"] for row in rows] == list(PHASE3_B2_CLAIM_IDS)
    assert gather_order == list(PHASE3_B2_CLAIM_IDS)
    assert len(rows) == DEVELOPMENT_CLAIM_BUDGET
    for row in rows:
        assert row["method_id"] == "V"
        assert row["adaptation"] == "V"
        assert row["system_id"] == "validator_v"
        assert row["label"] in NATIVE
        assert row["label_4way"] in FOUR_WAY
        assert row["inference_mode"] == "mock"
        assert row["evidence_scope"] == "D0_union_D1"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["method_id"] == "V"
    assert sidecar["input_source"] == "gather"
    assert sidecar["n_predictions"] == 20
    assert sidecar["claim_ids"] == list(PHASE3_B2_CLAIM_IDS)
    assert sidecar["run"]["run_id"].startswith("validator-v-gather-development-s0-n20-")
    assert "n3-" not in sidecar["run"]["run_id"]
    schema = json.loads((ROOT / "schemas" / "mavs_run_record.schema.json").read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(sidecar["run"])) == []
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with pytest.raises(SystemExit) as exited:
        with redirect_stdout(buffer):
            parse_args(["--help"])
    assert exited.value.code == 0
    help_out = buffer.getvalue()
    assert "scifact:0,scifact:2,scifact:4" in help_out
    assert "scifact:27" in help_out
    assert "--claim-ids" in help_out


def test_claim_ids_without_gather_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--claim-ids",
                "scifact:0",
                "--output",
                str(tmp_path / "x.jsonl"),
                "--run-sidecar",
                str(tmp_path / "x.json"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "x.jsonl").exists()


def test_phase3_claim_ids_match_development_manifest_prefix():
    retrieval = load_retrieval_config(ROOT / "configs" / "retrieval" / "scifact_bm25.yaml")
    from validator.retrieve import resolve_gather_claim_ids

    assert list(PHASE3_B2_CLAIM_IDS) == resolve_gather_claim_ids(retrieval, limit=20)
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert config["claim_ids"] == list(PHASE3_B2_CLAIM_IDS)


def test_live_is_refused_for_a_dry_run_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    assert (
        main(
            [
                "--config",
                str(CONFIG),
                "--live",
                "--limit",
                "1",
                "--output",
                str(tmp_path / "live.jsonl"),
                "--run-sidecar",
                str(tmp_path / "live-run.json"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "live.jsonl").exists()


def test_live_client_records_inference_mode_live(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    fixture = json.loads(CONFLICT.read_text(encoding="utf-8"))
    fixture["dry_run"] = False
    fixture_path = tmp_path / "live_report.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    config["reports"] = [str(fixture_path)]
    config["dry_run"] = True
    config_path = tmp_path / "v.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    class Fake:
        def complete(self, system_prompt: str, payload: dict) -> str:
            del system_prompt
            assert "asserted_answer" not in payload
            assert LEAK not in json.dumps(payload)
            span = payload["passages"][0]["span_id"]
            if "normalized_claim" not in payload:
                return json.dumps(
                    {"answer": "A passage addresses the topic.", "cited_span_ids": [span]}
                )
            return json.dumps(
                {
                    "label": "supported",
                    "cited_span_ids": [span],
                    "rationale_codes": ["live_model"],
                    "uncertainty_reasons": [],
                }
            )

    predictions = tmp_path / "predictions.jsonl"
    sidecar_path = tmp_path / "run.json"
    args = parse_args(
        [
            "--config",
            str(config_path),
            "--live",
            "--limit",
            "1",
            "--output",
            str(predictions),
            "--run-sidecar",
            str(sidecar_path),
        ]
    )
    execute(args, client=Fake())
    row = _rows(predictions)[0]
    assert row["inference_mode"] == "live"
    assert row["method_id"] == "V"
    assert row["label"] == "SUPPORT"
    assert row["label_4way"] == "supported"
    assert row["execution_status"] == "ok"
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["inference_mode"] == "live"
    assert sidecar["model_invoked"] is True
    assert load_live_settings(ROOT / "configs" / "judgment" / "fixture_live.yaml").model_id == (
        sidecar["run"]["model_id"]
    )


def test_smoke_script_exits_zero(tmp_path: Path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    env["VALIDATOR_V_SMOKE_OUT"] = str(tmp_path / "smoke")
    proc = subprocess.run(
        ["bash", str(ROOT / "scripts" / "validator_v_smoke.sh")],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert "validator v smoke OK" in proc.stdout
    assert (tmp_path / "smoke" / "predictions.jsonl").is_file()
    assert (tmp_path / "smoke" / "run.json").is_file()
