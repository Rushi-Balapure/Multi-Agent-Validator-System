"""Reference baselines B0, B1, B3, O, V-D1, and B2@k."""

from __future__ import annotations

from pathlib import Path

from validator.baselines.evidence import evidence_text, format_oracle_rationales
from validator.baselines.extract_vd1 import vd1_row
from validator.baselines.majority import choose_k, collapse_b2k, majority_label
from validator.baselines.single_judge import MockSingleJudge, run_single_judge
from validator.same_evidence.inputs import GoldEvidenceDoc, PredictInput, Rationale

DOC_HASH = "a" * 64


def _item(rationales: list[Rationale] | None = None) -> PredictInput:
    return PredictInput(
        claim_id="scifact:1",
        split_role="development",
        normalized_claim="Vitamin C shortens colds.",
        gold_evidence_bundle=[
            GoldEvidenceDoc(
                doc_id=10,
                title="Vitamin C trial",
                abstract=["Adults took vitamin C.", "Colds were shorter."],
                structured=False,
                rationales=rationales or [],
                snapshot_hash=DOC_HASH,
            )
        ],
        cited_doc_ids=[10],
        native_label_space="scifact_SUPPORT_CONTRADICT",
    )


def test_b0_evidence_is_empty_and_b1_keeps_full_abstracts():
    item = _item([Rationale(label="SUPPORT", sentences=[1])])
    assert evidence_text(item, "B0") == ""
    b1 = evidence_text(item, "B1")
    assert "Adults took vitamin C." in b1
    assert "Colds were shorter." in b1
    oracle = format_oracle_rationales(item)
    assert "Colds were shorter." in oracle
    assert "Adults took vitamin C." not in oracle


def test_mock_single_judge_is_deterministic():
    item = _item()
    prompt = "judge"
    first = run_single_judge(item, adaptation="B0", prompt=prompt, client=MockSingleJudge(0))
    second = run_single_judge(item, adaptation="B0", prompt=prompt, client=MockSingleJudge(0))
    assert first == second
    assert first["label"] in {"SUPPORT", "REFUTE", "NEI"}
    assert first["adaptation"] == "B0"
    assert first["execution_status"] == "ok"
    assert 0.0 <= first["confidence"] <= 1.0


def test_oracle_empty_when_nei_eligible():
    assert format_oracle_rationales(_item([])) == ""


def test_vd1_maps_four_way_without_a_new_run():
    row = vd1_row(
        {
            "claim_id": "scifact:1",
            "d1_label_4way": "supported",
            "execution_status": "ok",
            "inference_mode": "live",
        }
    )
    assert row["label"] == "SUPPORT"
    assert row["adaptation"] == "V-D1"
    assert row["method_id"] == "V-D1"


def test_majority_is_conservative_on_ties():
    assert majority_label(["SUPPORT", "REFUTE", "NEI"]) == "NEI"
    assert majority_label(["SUPPORT", "SUPPORT", "REFUTE"]) == "SUPPORT"
    assert choose_k(b2_tokens_per_claim=100, v_tokens_per_claim=350) == 4
    collapsed = collapse_b2k(
        [
            [{"claim_id": "c1", "label": "SUPPORT", "execution_status": "ok"}],
            [{"claim_id": "c1", "label": "NEI", "execution_status": "ok"}],
            [{"claim_id": "c1", "label": "NEI", "execution_status": "ok"}],
        ],
        k=3,
    )
    assert collapsed[0]["label"] == "NEI"
    assert collapsed[0]["adaptation"] == "B2@3"
