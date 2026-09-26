"""Fixture run of the staged judge: happy path, missing citation, four-way policy."""

from __future__ import annotations

import json
import socket
import urllib.request
from pathlib import Path

import pytest
import yaml

from validator.evidence_reader import compute_seal
from validator.fixture_pipeline import StagedVerdict, load_fixture, main, run_fixture
from validator.inference_client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL_ID,
    EndpointPolicyError,
    InferenceTransportError,
    LocalChatClient,
)
from validator.live_judgment import default_live_config, load_live_settings
from validator.same_evidence.b2 import EndpointUnavailable, OpenAICompatibleClient
from validator.label_policy import PassageView, decide_label
from validator.render import ClaimCard, RenderError, verify_explanations
from validator.schemas import EvidenceScope, ExecutionStatus, LabelSpace, ScientificLabel

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "judgment"
COMPLETE = FIXTURES / "complete.json"
MISSING = FIXTURES / "missing_citation.json"
COMPLETE_VERDICT = FIXTURES / "complete_verdict.json"
MISSING_VERDICT = FIXTURES / "missing_citation_verdict.json"
LEAK = "LEAK_ASSERTED_ANSWER"
PINNED_CORPUS_HASH = "b8d6c89624cb2ed74dee8938effc4f5d8bd2086887880af8110d64be4ceade62"
FOUR_WAY = {item.value for item in ScientificLabel}


def test_label_policy_covers_the_four_labels():
    claim = "In the mouse model, compound MX-42 increased memory retention."
    support = PassageView(
        span_id="D1:1:0-10",
        text=(
            "In the mouse model, compound MX-42 increased memory retention "
            "compared with vehicle."
        ),
    )
    contradict = PassageView(
        span_id="D1:2:0-10",
        text=(
            "In the mouse model, compound MX-42 decreased memory retention "
            "compared with vehicle."
        ),
    )
    negated = PassageView(
        span_id="D1:3:0-10",
        text=(
            "In the mouse model, compound MX-42 did not increase memory retention "
            "compared with vehicle."
        ),
    )
    unrelated = PassageView(
        span_id="D1:4:0-10",
        text="A separate yeast assay reported unchanged glucose uptake under solvent control.",
    )
    causal = "Compound MX-42 caused increased memory retention in the mouse model."

    supported = decide_label(claim, [support, unrelated])
    assert supported.label is ScientificLabel.SUPPORTED
    assert supported.cited_span_ids == ["D1:1:0-10"]

    contradicted = decide_label(claim, [contradict])
    assert contradicted.label is ScientificLabel.CONTRADICTED
    assert decide_label(claim, [negated]).label is ScientificLabel.CONTRADICTED

    unaddressed = decide_label(claim, [unrelated])
    assert unaddressed.label is ScientificLabel.UNADDRESSED
    assert unaddressed.cited_span_ids == []

    measured = PassageView(
        span_id="D1:5:0-10",
        text="In the mouse model, compound MX-42 memory retention was measured.",
    )
    inconclusive = decide_label(claim, [measured])
    assert inconclusive.label is ScientificLabel.UNDERDETERMINED
    assert "inconclusive_relevant_evidence" in inconclusive.rationale_codes

    conflict = decide_label(claim, [support, contradict])
    assert conflict.label is ScientificLabel.UNDERDETERMINED
    assert "conflicting_results" in conflict.rationale_codes

    overreach = decide_label(causal, [support])
    assert overreach.label is ScientificLabel.UNDERDETERMINED
    assert "causal_overreach" in overreach.rationale_codes


def test_complete_fixture_bundle_uses_locked_corpus_hash():
    corpus = yaml.safe_load((ROOT / "configs" / "corpus" / "scifact.yaml").read_text(encoding="utf-8"))
    fixture = load_fixture(COMPLETE)
    assert fixture.d1_bundle.corpus_hash == corpus["corpus_hash"] == PINNED_CORPUS_HASH
    assert fixture.claim.claim_id == "scifact:900042"
    assert fixture.d0_evidence
    assert all(item.access_scope.value == "D0" for item in fixture.d0_evidence)
    assert all(item.provenance is not None and item.provenance.value == "original" for item in fixture.d0_evidence)
    assert all(item.access_scope.value == "D1" for item in fixture.d1_bundle.passages)
    assert all(
        item.provenance is not None and item.provenance.value == "independent"
        for item in fixture.d1_bundle.passages
    )


def test_reader_seals_before_the_judge_sees_the_claim(monkeypatch: pytest.MonkeyPatch):
    import validator.fixture_pipeline as pipeline

    events: list[str] = []
    real_read = pipeline.read_evidence
    real_judge = pipeline.judge_claim

    def wrapped_read(payload):
        events.append("read")
        assert "asserted_answer" not in payload
        assert LEAK not in json.dumps(payload)
        return real_read(payload)

    def wrapped_judge(claim, sealed, bundle):
        events.append("judge")
        assert events == ["read", "judge"]
        assert sealed.seal == compute_seal(
            sealed.neutral_question, sealed.answer, sealed.cited_span_ids
        )
        assert LEAK not in sealed.answer
        return real_judge(claim, sealed, bundle)

    monkeypatch.setattr(pipeline, "read_evidence", wrapped_read)
    monkeypatch.setattr(pipeline, "judge_claim", wrapped_judge)
    verdict = pipeline.run_fixture(load_fixture(COMPLETE))
    assert events == ["read", "judge"]
    assert verdict.sealed_reader.seal


def test_complete_fixture_emits_four_way_verdict():
    verdict = run_fixture(load_fixture(COMPLETE))
    assert len(verdict.judgments) == 2
    by_scope = {item.evidence_scope: item for item in verdict.judgments}
    d1 = by_scope[EvidenceScope.D1]
    d0 = by_scope[EvidenceScope.D0]
    assert d1.label_space is LabelSpace.MAVS_FOUR_WAY
    assert d0.label_space is LabelSpace.MAVS_FOUR_WAY
    assert d1.label in FOUR_WAY
    assert d0.label in FOUR_WAY
    assert d1.label == ScientificLabel.SUPPORTED.value
    assert d0.label == ScientificLabel.SUPPORTED.value
    assert d1.execution_status is ExecutionStatus.COMPLETED
    assert d0.execution_status is ExecutionStatus.COMPLETED
    assert d1.label not in {item.value for item in ExecutionStatus}
    assert d1.cited_span_ids
    assert verdict.citation_flags
    assert verdict.citation_flags[0].adequacy == "adequate"
    assert verdict.reconciler_notes
    report = verdict.report_verdict
    assert report.claim_coverage["claims_judged"] == 1
    assert report.central_claim_outcomes[0]["agreed_label"] == "supported"
    assert report.inference_link_status[0]["status"] == "valid"
    assert report.conflicts_d0_d1 == []
    assert report.display_explanation
    assert report.limitations
    assert "Live model prompts" in " ".join(report.limitations)
    assert LEAK not in verdict.model_dump_json()
    committed = json.loads(COMPLETE_VERDICT.read_text(encoding="utf-8"))
    assert json.loads(verdict.model_dump_json()) == committed
    assert StagedVerdict.model_validate(committed).sealed_reader.seal == verdict.sealed_reader.seal


def test_missing_citation_fixture_keeps_structured_failure():
    verdict = run_fixture(load_fixture(MISSING))
    by_scope = {item.evidence_scope: item for item in verdict.judgments}
    d1 = by_scope[EvidenceScope.D1]
    d0 = by_scope[EvidenceScope.D0]
    assert d1.label == ScientificLabel.SUPPORTED.value
    assert d1.execution_status is ExecutionStatus.COMPLETED
    assert d0.label == ScientificLabel.UNADDRESSED.value
    assert d0.execution_status is ExecutionStatus.FAILED
    assert d0.label != d1.label
    assert verdict.citation_flags[0].adequacy == "inadequate"
    assert "missing_required_citation" in verdict.citation_flags[0].defects
    assert verdict.report_verdict.conflicts_d0_d1
    assert verdict.report_verdict.inference_link_status[0]["status"] == "unresolved"
    assert verdict.reconciler_notes
    assert verdict.claim_card.original_citations == "inadequate"
    assert "D1 was not used to repair D0" in " ".join(verdict.report_verdict.limitations)
    assert LEAK not in verdict.model_dump_json()
    committed = json.loads(MISSING_VERDICT.read_text(encoding="utf-8"))
    assert json.loads(verdict.model_dump_json()) == committed
    assert StagedVerdict.model_validate(committed).judgments


def test_cli_writes_verdict_json(tmp_path: Path):
    output = tmp_path / "verdict.json"
    assert main(["--fixture", str(COMPLETE), "--output", str(output)]) == 0
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["judgments"][0]["label"] == "supported"
    assert payload["citation_flags"]
    assert payload["reconciler_notes"]
    assert payload["report_verdict"]["display_explanation"]


def test_renderer_rejects_an_explanatory_sentence_without_a_span():
    card = ClaimCard(
        claim="In the mouse model, compound MX-42 increased memory retention.",
        evidence_verdict="Evidence verdict: supported.",
        why=["Why: the study showed a benefit."],
        what_is_uncertain="None recorded.",
        search_scope="corpus hash abc; 1 independent passages; retrieval round 1.",
        original_citations="adequate",
        next_useful_check="No further check is recorded on this claim.",
        display_text="Why: the study showed a benefit.",
    )
    with pytest.raises(RenderError):
        verify_explanations(card, {"D1:880042:0-1"})


def test_judgment_modules_do_not_call_the_retriever():
    root = ROOT / "src" / "validator"
    names = [
        "label_policy.py",
        "evidence_reader.py",
        "judge.py",
        "citation_auditor.py",
        "reconcile.py",
        "render.py",
        "fixture_pipeline.py",
        "inference_client.py",
        "live_judgment.py",
    ]
    for name in names:
        text = (root / name).read_text(encoding="utf-8")
        assert "validator.retrieve" not in text
        assert "retrieval.bm25" not in text
        assert "vllm" not in text.casefold()


def _block_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_network(*_args, **_kwargs):
        raise AssertionError("fixture path opened a network connection")

    monkeypatch.setattr(urllib.request, "urlopen", fail_network)
    monkeypatch.setattr(socket, "create_connection", fail_network)


def test_offline_fixture_does_not_open_a_socket(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    verdict = run_fixture(load_fixture(COMPLETE))
    assert verdict.judgments[0].label == "supported"
    assert "Live model prompts" in " ".join(verdict.report_verdict.limitations)


def test_cli_help_documents_lm_studio_defaults(capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    assert DEFAULT_MODEL_ID in text
    assert "qwen2.5-coder-1.5b-instruct" in text
    assert DEFAULT_BASE_URL in text
    assert "http://192.168.1.10:1234/v1" in text
    assert "--live" in text


def test_live_config_points_at_lm_studio_loopback():
    loaded = load_live_settings(default_live_config())
    assert loaded.model_id == DEFAULT_MODEL_ID == "qwen2.5-coder-1.5b-instruct"
    assert loaded.base_url == DEFAULT_BASE_URL == "http://127.0.0.1:1234/v1"
    assert "asserted_answer" not in loaded.reader_prompt
    assert LEAK not in loaded.reader_prompt
    assert LEAK not in loaded.judge_prompt


def test_public_endpoint_is_refused_before_a_socket(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(EndpointPolicyError):
        LocalChatClient(
            base_url="https://api.openai.com/v1",
            model_id=DEFAULT_MODEL_ID,
            temperature=0,
            timeout_seconds=1,
        )
    with pytest.raises(EndpointPolicyError):
        load_live_settings(default_live_config(), base_url="http://8.8.8.8/v1")


def test_private_lan_endpoint_is_accepted_without_a_socket(monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    client = LocalChatClient(
        base_url="http://192.168.1.10:1234/v1",
        model_id=DEFAULT_MODEL_ID,
        temperature=0,
        timeout_seconds=1,
    )
    assert client.base_url == "http://192.168.1.10:1234/v1"
    loaded = load_live_settings(default_live_config(), base_url="http://10.1.2.3:1234/v1")
    assert loaded.base_url == "http://10.1.2.3:1234/v1"


def test_baseline_timeout_is_not_a_scientific_label(monkeypatch: pytest.MonkeyPatch):
    def boom(self, system_prompt: str, payload: dict) -> str:
        del self, system_prompt, payload
        raise EndpointUnavailable("timed out") from TimeoutError("timed out")

    monkeypatch.setattr(OpenAICompatibleClient, "_chat", boom)
    client = LocalChatClient(
        base_url=DEFAULT_BASE_URL,
        model_id=DEFAULT_MODEL_ID,
        temperature=0,
        timeout_seconds=1,
    )
    with pytest.raises(InferenceTransportError) as exc:
        client.complete("system", {"neutral_question": "q", "passages": []})
    assert exc.value.timed_out is True


def _is_reader(payload: dict) -> bool:
    return "normalized_claim" not in payload


def _is_judge(payload: dict) -> bool:
    """The claim-visible D1 judge is the only role that sees the sealed reading."""
    return "normalized_claim" in payload and "sealed_reader" in payload


def _is_citation_audit(payload: dict) -> bool:
    """The D0 auditor sees the claim and the original citations, never D1."""
    return "normalized_claim" in payload and "sealed_reader" not in payload


class _RecordingClient:
    def __init__(self, judge_text: str | None = None, audit_text: str | None = None) -> None:
        self.judge_text = judge_text
        self.audit_text = audit_text
        self.payloads: list[dict] = []
        self.prompts: list[str] = []

    def complete(self, system_prompt: str, payload: dict) -> str:
        self.prompts.append(system_prompt)
        self.payloads.append(payload)
        if _is_reader(payload):
            return _reader_json(payload)
        if _is_citation_audit(payload):
            return self.audit_text if self.audit_text is not None else _audit_json(payload)
        if self.judge_text is None:
            raise AssertionError("judge was called")
        return self.judge_text


def _reader_json(payload: dict) -> str:
    span = payload["passages"][0]["span_id"]
    return json.dumps(
        {
            "answer": "The mouse-model passage reports increased memory retention.",
            "cited_span_ids": [span],
        }
    )


def _audit_json(payload: dict, label: str = "supported") -> str:
    spans = [passage["span_id"] for passage in payload["passages"]]
    return json.dumps(
        {
            "label": label,
            "rationale_codes": ["model_citation_audit"],
            "cited_span_ids": spans[:1],
            "uncertainty_reasons": [],
            "citations": [
                {"span_id": span, "adequacy": "adequate", "defects": []} for span in spans
            ],
        }
    )


def test_live_reader_omits_asserted_answer_and_keeps_a_parsed_label():
    fixture = load_fixture(COMPLETE)

    class Client(_RecordingClient):
        def complete(self, system_prompt: str, payload: dict) -> str:
            self.prompts.append(system_prompt)
            self.payloads.append(payload)
            if _is_reader(payload):
                return _reader_json(payload)
            if _is_citation_audit(payload):
                return _audit_json(payload)
            span = payload["passages"][0]["span_id"]
            return json.dumps(
                {
                    "label": "contradicted",
                    "rationale_codes": ["model_conflict"],
                    "cited_span_ids": [span],
                    "uncertainty_reasons": [],
                }
            )

    client = Client()
    verdict = run_fixture(fixture, live=load_live_settings(default_live_config()), client=client)
    reader_payload = next(item for item in client.payloads if _is_reader(item))
    judge_payload = next(item for item in client.payloads if _is_judge(item))
    audit_payload = next(item for item in client.payloads if _is_citation_audit(item))
    assert set(reader_payload) == {"neutral_question", "passages"}
    assert "asserted_answer" not in reader_payload
    assert "asserted_answer" not in judge_payload
    # The D0 auditor is claim-visible but must never receive the sealed D1 reading.
    assert set(audit_payload) == {"claim_id", "normalized_claim", "passages"}
    blob = json.dumps(client.payloads)
    assert LEAK not in blob
    assert LEAK not in "".join(client.prompts)
    by_scope = {item.evidence_scope: item for item in verdict.judgments}
    assert by_scope[EvidenceScope.D1].label == ScientificLabel.CONTRADICTED.value
    assert by_scope[EvidenceScope.D1].execution_status is ExecutionStatus.COMPLETED
    assert by_scope[EvidenceScope.D0].label == ScientificLabel.SUPPORTED.value
    assert by_scope[EvidenceScope.D0].execution_status is ExecutionStatus.COMPLETED
    assert LEAK not in verdict.model_dump_json()


@pytest.mark.parametrize(
    "judge_text",
    [
        "GARBAGE_LABEL_SUPPORT_PLEASE the claim is totally supported",
        json.dumps(
            {
                "label": "SUPPORT",
                "rationale_codes": ["native"],
                "cited_span_ids": [],
                "uncertainty_reasons": [],
            }
        ),
        json.dumps({"label": "supported", "rationale_codes": ["missing_spans"]}),
    ],
)
def test_live_judge_garbage_fails_closed(judge_text: str):
    fixture = load_fixture(COMPLETE)
    client = _RecordingClient(judge_text)
    verdict = run_fixture(fixture, live=load_live_settings(default_live_config()), client=client)
    by_scope = {item.evidence_scope: item for item in verdict.judgments}
    d1 = by_scope[EvidenceScope.D1]
    assert d1.execution_status is ExecutionStatus.FAILED
    assert d1.label == ScientificLabel.UNADDRESSED.value
    assert d1.rationale_codes == ["live_parse_failed"]
    assert d1.label not in {"failed", "timeout", "completed"}
    dumped = verdict.model_dump_json()
    assert "GARBAGE_LABEL_SUPPORT_PLEASE" not in dumped
    assert "totally supported" not in dumped
    assert "fail-closed placeholder" in " ".join(verdict.report_verdict.limitations)


def test_live_reader_garbage_does_not_call_the_judge():
    fixture = load_fixture(COMPLETE)

    class Client:
        def __init__(self) -> None:
            self.payloads: list[dict] = []

        def complete(self, system_prompt: str, payload: dict) -> str:
            del system_prompt
            self.payloads.append(payload)
            if _is_judge(payload):
                raise AssertionError("judge was called")
            if _is_citation_audit(payload):
                return _audit_json(payload)
            return "GARBAGE_READER_OUTPUT"

    client = Client()
    verdict = run_fixture(fixture, live=load_live_settings(default_live_config()), client=client)
    # A failed D1 reader must not reach the D1 judge, and must not suppress the
    # independent D0 audit.
    assert not any(_is_judge(item) for item in client.payloads)
    reader_payload = next(item for item in client.payloads if _is_reader(item))
    assert any(_is_citation_audit(item) for item in client.payloads)
    assert "asserted_answer" not in reader_payload
    assert LEAK not in json.dumps(client.payloads)
    d1 = next(item for item in verdict.judgments if item.evidence_scope is EvidenceScope.D1)
    assert d1.execution_status is ExecutionStatus.FAILED
    assert d1.label == ScientificLabel.UNADDRESSED.value
    assert "GARBAGE_READER_OUTPUT" not in verdict.model_dump_json()
    assert verdict.sealed_reader.answer.startswith("Live evidence reader failed closed")


def test_live_d0_audit_is_model_based_and_never_sees_d1():
    """D0 and D1 must be judged by one mechanism, or reconciliation is an artifact."""
    fixture = load_fixture(COMPLETE)
    client = _RecordingClient(
        judge_text=json.dumps(
            {
                "label": "supported",
                "rationale_codes": ["model_d1"],
                "cited_span_ids": [],
                "uncertainty_reasons": [],
            }
        )
    )
    verdict = run_fixture(fixture, live=load_live_settings(default_live_config()), client=client)
    audit_payload = next(item for item in client.payloads if _is_citation_audit(item))
    d1_span_ids = {
        passage["span_id"]
        for item in client.payloads
        if _is_judge(item)
        for passage in item["passages"]
    }
    audit_span_ids = {passage["span_id"] for passage in audit_payload["passages"]}
    assert audit_span_ids
    assert audit_span_ids.isdisjoint(d1_span_ids)
    assert "sealed_reader" not in audit_payload
    by_scope = {item.evidence_scope: item for item in verdict.judgments}
    d0 = by_scope[EvidenceScope.D0]
    assert d0.execution_status is ExecutionStatus.COMPLETED
    assert d0.rationale_codes == ["model_citation_audit"]
    assert all(flag.adequacy == "adequate" for flag in verdict.citation_flags)


@pytest.mark.parametrize(
    "audit_text",
    [
        "GARBAGE_D0_AUDIT the citation is perfect",
        json.dumps({"label": "SUPPORT", "rationale_codes": [], "cited_span_ids": []}),
        json.dumps(
            {
                "label": "supported",
                "rationale_codes": ["ok"],
                "cited_span_ids": [],
                "uncertainty_reasons": [],
                "citations": [{"span_id": "D0:999:0-1", "adequacy": "adequate"}],
            }
        ),
    ],
)
def test_live_d0_audit_garbage_fails_closed(audit_text: str):
    fixture = load_fixture(COMPLETE)
    client = _RecordingClient(
        judge_text=json.dumps(
            {
                "label": "supported",
                "rationale_codes": ["model_d1"],
                "cited_span_ids": [],
                "uncertainty_reasons": [],
            }
        ),
        audit_text=audit_text,
    )
    verdict = run_fixture(fixture, live=load_live_settings(default_live_config()), client=client)
    d0 = next(item for item in verdict.judgments if item.evidence_scope is EvidenceScope.D0)
    assert d0.execution_status is ExecutionStatus.FAILED
    assert d0.label == ScientificLabel.UNADDRESSED.value
    assert d0.label in FOUR_WAY
    assert "GARBAGE_D0_AUDIT" not in verdict.model_dump_json()
    assert "citation is perfect" not in verdict.model_dump_json()


def test_live_d0_audit_adequacy_comes_from_the_model():
    fixture = load_fixture(COMPLETE)

    class Client(_RecordingClient):
        def complete(self, system_prompt: str, payload: dict) -> str:
            self.prompts.append(system_prompt)
            self.payloads.append(payload)
            if _is_reader(payload):
                return _reader_json(payload)
            if _is_citation_audit(payload):
                spans = [passage["span_id"] for passage in payload["passages"]]
                return json.dumps(
                    {
                        "label": "underdetermined",
                        "rationale_codes": ["population_transfer"],
                        "cited_span_ids": spans[:1],
                        "uncertainty_reasons": ["scope mismatch"],
                        "citations": [
                            {
                                "span_id": span,
                                "adequacy": "unverifiable",
                                "defects": ["population_transfer"],
                            }
                            for span in spans
                        ],
                    }
                )
            return json.dumps(
                {
                    "label": "supported",
                    "rationale_codes": ["model_d1"],
                    "cited_span_ids": [],
                    "uncertainty_reasons": [],
                }
            )

    client = Client()
    verdict = run_fixture(fixture, live=load_live_settings(default_live_config()), client=client)
    d0 = next(item for item in verdict.judgments if item.evidence_scope is EvidenceScope.D0)
    assert d0.label == ScientificLabel.UNDERDETERMINED.value
    assert d0.uncertainty_reasons == ["scope mismatch"]
    assert verdict.citation_flags
    assert all(flag.adequacy == "unverifiable" for flag in verdict.citation_flags)
    assert all(flag.defects == ["population_transfer"] for flag in verdict.citation_flags)


def test_live_timeout_sets_execution_status_timeout():
    fixture = load_fixture(COMPLETE)

    class TimeoutClient:
        def complete(self, system_prompt: str, payload: dict) -> str:
            del system_prompt, payload
            raise InferenceTransportError("timed out", timed_out=True)

    verdict = run_fixture(
        fixture,
        live=load_live_settings(default_live_config()),
        client=TimeoutClient(),
    )
    d1 = next(item for item in verdict.judgments if item.evidence_scope is EvidenceScope.D1)
    assert d1.execution_status is ExecutionStatus.TIMEOUT
    assert d1.label == ScientificLabel.UNADDRESSED.value
    assert d1.rationale_codes == ["live_timeout"]


def test_cli_live_refuses_a_public_host(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    _block_network(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr("validator.fixture_pipeline.load_repo_dotenv", lambda root=None: None)
    output = tmp_path / "verdict.json"
    assert (
        main(
            [
                "--fixture",
                str(COMPLETE),
                "--live",
                "--base-url",
                "https://api.openai.com/v1",
                "--output",
                str(output),
            ]
        )
        == 2
    )
    assert not output.exists()


def test_cli_rejects_endpoint_flags_without_live():
    with pytest.raises(SystemExit) as exc:
        main(["--fixture", str(COMPLETE), "--base-url", DEFAULT_BASE_URL])
    assert exc.value.code == 2


def test_cli_live_writes_a_failed_verdict_without_calling_the_network(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    _block_network(monkeypatch)
    seen: dict[str, str] = {}

    class Fake:
        def __init__(self, *, base_url: str, model_id: str, temperature: float, timeout_seconds: float) -> None:
            del temperature, timeout_seconds
            seen["base_url"] = base_url
            seen["model_id"] = model_id

        def complete(self, system_prompt: str, payload: dict) -> str:
            del system_prompt, payload
            return "GARBAGE_CLI not a judgment"

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    monkeypatch.setattr("validator.fixture_pipeline.load_repo_dotenv", lambda root=None: None)
    monkeypatch.setattr("validator.live_judgment.LocalChatClient", Fake)
    output = tmp_path / "verdict.json"
    assert main(["--fixture", str(COMPLETE), "--live", "--output", str(output)]) == 1
    assert seen == {"base_url": DEFAULT_BASE_URL, "model_id": DEFAULT_MODEL_ID}
    text = output.read_text(encoding="utf-8")
    payload = json.loads(text)
    d1 = next(item for item in payload["judgments"] if item["evidence_scope"] == "D1")
    assert d1["execution_status"] == "failed"
    assert d1["label"] == "unaddressed"
    assert "GARBAGE_CLI" not in text
