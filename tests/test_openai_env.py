"""OPENAI_API_KEY / OPENAI_MODEL opt-in for the official OpenAI endpoint.

Arbitrary public hosts stay refused. The official host is allowed only when a
key is present. Live runners apply the env model without writing the key into
configs or logs.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from validator.inference_client import EndpointPolicyError, LocalChatClient
from validator.live_judgment import default_live_config, load_live_settings
from validator.same_evidence.b2 import (
    OPENAI_CLOUD_BASE_URL,
    BaselineDataError,
    OpenAICompatibleClient,
    apply_openai_env,
    assert_local_or_private,
    load_repo_dotenv,
)
from validator.same_evidence.runner import main as b2_main
from validator.validator_v.runner import execute as v_execute
from validator.validator_v.runner import parse_args as v_parse_args

ROOT = Path(__file__).resolve().parents[1]


def test_openai_cloud_is_refused_without_a_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(BaselineDataError, match="OPENAI_API_KEY"):
        assert_local_or_private(OPENAI_CLOUD_BASE_URL)
    with pytest.raises(EndpointPolicyError):
        LocalChatClient(
            base_url=OPENAI_CLOUD_BASE_URL,
            model_id="gpt-6-luna",
            temperature=0,
            timeout_seconds=1,
        )


def test_openai_cloud_is_accepted_when_a_key_is_set(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    assert_local_or_private(OPENAI_CLOUD_BASE_URL)
    client = LocalChatClient(
        base_url=OPENAI_CLOUD_BASE_URL,
        model_id="gpt-6-luna",
        temperature=0,
        timeout_seconds=1,
    )
    assert client.base_url == OPENAI_CLOUD_BASE_URL
    assert client.model_id == "gpt-6-luna"
    live = OpenAICompatibleClient(
        base_url=OPENAI_CLOUD_BASE_URL,
        model_id="gpt-6-luna",
        temperature=0,
        timeout_seconds=1,
    )
    assert live.inference_mode == "live"
    assert live.model_id == "gpt-6-luna"


def test_other_public_hosts_stay_refused_even_with_a_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    for url in ("https://example.com/v1", "http://8.8.8.8/v1", "https://api.anthropic.com/v1"):
        with pytest.raises(BaselineDataError, match="refusing endpoint"):
            assert_local_or_private(url)


def test_openai_cloud_omits_temperature(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    cloud = OpenAICompatibleClient(
        base_url=OPENAI_CLOUD_BASE_URL,
        model_id="gpt-6-luna",
        temperature=0,
        timeout_seconds=1,
    )
    body = cloud._completion_body("system", {"neutral_question": "q"})
    assert "temperature" not in body
    assert body["model"] == "gpt-6-luna"
    local = OpenAICompatibleClient(
        base_url="http://127.0.0.1:1234/v1",
        model_id="qwen2.5-coder-1.5b-instruct",
        temperature=0,
        timeout_seconds=1,
    )
    assert local._completion_body("system", {"neutral_question": "q"})["temperature"] == 0


def test_apply_openai_env_uses_cloud_host_and_env_model(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    base_url, model_id = apply_openai_env("http://127.0.0.1:1234/v1", "qwen2.5-coder-1.5b-instruct")
    assert base_url == OPENAI_CLOUD_BASE_URL
    assert model_id == "gpt-6-luna"


def test_apply_openai_env_leaves_local_defaults_without_both_vars(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    base_url, model_id = apply_openai_env("http://127.0.0.1:1234/v1", "qwen2.5-coder-1.5b-instruct")
    assert base_url == "http://127.0.0.1:1234/v1"
    assert model_id == "qwen2.5-coder-1.5b-instruct"
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    base_url, model_id = apply_openai_env("http://127.0.0.1:1234/v1", "qwen2.5-coder-1.5b-instruct")
    assert base_url == "http://127.0.0.1:1234/v1"
    assert model_id == "qwen2.5-coder-1.5b-instruct"


def test_load_repo_dotenv_fills_missing_vars_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "configs" / "corpus").mkdir(parents=True)
    (tmp_path / "manifests" / "scifact").mkdir(parents=True)
    (tmp_path / "configs" / "corpus" / "scifact.yaml").write_text("name: scifact\n", encoding="utf-8")
    (tmp_path / ".env").write_text(
        "OPENAI_API_KEY=sk-from-file\nOPENAI_MODEL=gpt-6-luna\nALREADY_SET=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setenv("ALREADY_SET", "from-process")
    load_repo_dotenv(tmp_path)
    import os

    assert os.environ["OPENAI_API_KEY"] == "sk-from-file"
    assert os.environ["OPENAI_MODEL"] == "gpt-6-luna"
    assert os.environ["ALREADY_SET"] == "from-process"


def test_live_settings_accept_openai_cloud_with_a_key(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    loaded = load_live_settings(
        default_live_config(),
        base_url=OPENAI_CLOUD_BASE_URL,
        model_id="gpt-6-luna",
    )
    assert loaded.base_url == OPENAI_CLOUD_BASE_URL
    assert loaded.model_id == "gpt-6-luna"


def test_dry_run_allows_openai_url_when_a_key_is_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr("validator.same_evidence.runner.load_repo_dotenv", lambda root=None: None)
    config = yaml.safe_load((ROOT / "configs" / "baseline" / "same_evidence_b2.yaml").read_text(encoding="utf-8"))
    config["base_url"] = OPENAI_CLOUD_BASE_URL
    config["model_id"] = "gpt-6-luna"
    path = tmp_path / "openai.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    b2_main(
        [
            "--config",
            str(path),
            "--dry-run",
            "--limit",
            "1",
            "--output",
            str(tmp_path / "predictions.jsonl"),
            "--run-sidecar",
            str(tmp_path / "run.json"),
        ]
    )
    sidecar = yaml.safe_load((tmp_path / "run.json").read_text(encoding="utf-8"))
    assert sidecar["inference_mode"] == "mock"
    assert sidecar["run"]["model_id"] == "gpt-6-luna"


def test_live_v_sidecar_records_env_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-6-luna")
    monkeypatch.setattr("validator.validator_v.runner.load_repo_dotenv", lambda root=None: None)

    def fail_network(*_args, **_kwargs):
        raise AssertionError("live env test opened a network connection")

    monkeypatch.setattr("urllib.request.urlopen", fail_network)

    fixture = json.loads((ROOT / "tests" / "fixtures" / "judgment" / "e2e_conflict.json").read_text(encoding="utf-8"))
    fixture["dry_run"] = False
    fixture_path = tmp_path / "live_report.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    config = yaml.safe_load((ROOT / "configs" / "validator_v" / "development.yaml").read_text(encoding="utf-8"))
    config["reports"] = [str(fixture_path)]
    config["dry_run"] = True
    config_path = tmp_path / "v.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    class Fake:
        def complete(self, system_prompt: str, payload: dict) -> str:
            del system_prompt
            span = payload["passages"][0]["span_id"]
            if "normalized_claim" not in payload:
                return json.dumps(
                    {"answer": "A passage addresses the topic.", "cited_span_ids": [span]}
                )
            if "sealed_reader" not in payload:
                return json.dumps(
                    {
                        "label": "supported",
                        "cited_span_ids": [span],
                        "rationale_codes": ["live_model"],
                        "uncertainty_reasons": [],
                        "citations": [{"span_id": span, "adequacy": "adequate", "defects": []}],
                    }
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
    args = v_parse_args(
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
    v_execute(args, client=Fake())
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert sidecar["inference_mode"] == "live"
    assert sidecar["run"]["model_id"] == "gpt-6-luna"
