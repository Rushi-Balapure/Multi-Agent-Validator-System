"""One-call claim-visible judge used by B0, B1, B3, and the oracle."""

from __future__ import annotations

import hashlib
from typing import Any, Protocol

from validator.baselines.evidence import ADAPTATIONS, evidence_text
from validator.retrieval.models import EvidenceBundle
from validator.same_evidence.b2 import LabelError, extract_json_object, normalize_label
from validator.same_evidence.inputs import PredictInput

PREDICTION_LABELS = ("SUPPORT", "REFUTE", "NEI")


class ChatLike(Protocol):
    inference_mode: str

    def _chat(self, system_prompt: str, payload: dict) -> str:
        ...


class MockSingleJudge:
    """Deterministic offline labels. Gold rationales are not inputs to the hash."""

    inference_mode = "mock"

    def __init__(self, seed: int) -> None:
        self.seed = seed

    def _chat(self, system_prompt: str, payload: dict) -> str:
        material = "\n".join(
            [
                str(self.seed),
                str(payload.get("claim_id", "")),
                str(payload.get("adaptation", "")),
                str(payload.get("claim", "")),
                str(payload.get("evidence", "")),
                system_prompt[:24],
            ]
        )
        digest = hashlib.sha256(material.encode("utf-8")).digest()
        label = PREDICTION_LABELS[digest[0] % 3]
        confidence = (digest[1] % 100) / 100.0
        return (
            f'{{"label": "{label}", "rationale": "mock-{payload.get("adaptation")}: {label}", '
            f'"confidence": {confidence}}}'
        )


def parse_judge_response(raw: str) -> tuple[str, str, float | None]:
    parsed = extract_json_object(raw)
    rationale = parsed.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise LabelError("judge response is missing a rationale")
    confidence = parsed.get("confidence")
    if confidence is not None:
        try:
            confidence_f = float(confidence)
        except (TypeError, ValueError) as exc:
            raise LabelError("judge confidence is not a number") from exc
        if not 0.0 <= confidence_f <= 1.0:
            raise LabelError("judge confidence must be between 0 and 1")
    else:
        confidence_f = None
    return normalize_label(str(parsed.get("label", ""))), rationale.strip(), confidence_f


def run_single_judge(
    item: PredictInput,
    *,
    adaptation: str,
    prompt: str,
    client: ChatLike,
    d1_bundle: EvidenceBundle | None = None,
) -> dict[str, Any]:
    if adaptation not in ADAPTATIONS:
        raise LabelError(f"unknown adaptation {adaptation!r}")
    evidence = evidence_text(item, adaptation, d1_bundle=d1_bundle)
    payload = {
        "claim_id": item.claim_id,
        "claim": item.normalized_claim,
        "adaptation": adaptation,
        "evidence": evidence,
    }
    raw = client._chat(prompt, payload)
    label, rationale, confidence = parse_judge_response(raw)
    return {
        "claim_id": item.claim_id,
        "label": label,
        "rationale": rationale,
        "adaptation": adaptation,
        "method_id": adaptation,
        "system_id": "reference_baseline",
        "confidence": confidence,
        "inference_mode": client.inference_mode,
        "execution_status": "ok",
        "n_evidence_chars": len(evidence),
    }
