"""Official label-only scores, retrieval, calibration, risk-coverage, failures."""

from __future__ import annotations

from evaluation.calibration import (
    apply_temperature,
    brier_score,
    ece,
    fit_temperature,
    nll,
    verbalized_distribution,
)
from evaluation.failures import breakdown
from evaluation.retrieval_metrics import document_overlap, recall_at_k
from evaluation.risk_coverage import risk_coverage_curve, selective_accuracy
from evaluation.scifact_official import official_label_only_scores, to_official_prediction


def test_official_adapter_uses_empty_evidence_and_label_only_accuracy():
    rows = [
        {"claim_id": "scifact:2", "label": "SUPPORT", "label_gold": "SUPPORT"},
        {"claim_id": "scifact:4", "label": "REFUTE", "label_gold": "CONTRADICT"},
        {"claim_id": "scifact:6", "label": "SUPPORT", "label_gold": "NEI"},
    ]
    official = [to_official_prediction(row) for row in rows]
    assert official[0]["predicted_evidence"] == {}
    assert official[1]["predicted_label"] == "CONTRADICT"
    scores = official_label_only_scores(rows)
    assert scores["n_scored"] == 3
    assert scores["accuracy"] == 2 / 3


def test_recall_at_k_and_overlap():
    assert recall_at_k([1, 2, 3], [3, 9], k=2) == 0.0
    assert recall_at_k([1, 2, 3], [3, 9], k=3) == 0.5
    overlap = document_overlap([1, 2], [2, 3])
    assert overlap["n_overlap"] == 1
    assert overlap["jaccard"] == 1 / 3


def test_calibration_and_risk_coverage():
    gold = ["SUPPORT", "NEI", "REFUTE"]
    probs = [
        verbalized_distribution("SUPPORT", 0.9),
        verbalized_distribution("NEI", 0.6),
        verbalized_distribution("SUPPORT", 0.8),
    ]
    assert brier_score(probs, gold) > 0
    assert nll(probs, gold) > 0
    assert 0.0 <= ece(probs, gold) <= 1.0
    temperature = fit_temperature(probs, gold)
    calibrated = apply_temperature(probs, temperature)
    assert len(calibrated) == 3
    curve = risk_coverage_curve([True, True, False], [0.9, 0.6, 0.8])
    assert curve[0]["coverage"] == 1 / 3
    selected = selective_accuracy([True, False], [0.9, 0.1], threshold=0.5)
    assert selected["coverage"] == 0.5
    assert selected["accuracy"] == 1.0


def test_failure_breakdown_describes_rq2():
    report = breakdown(
        [
            {
                "label": "NEI",
                "label_4way": "unaddressed",
                "execution_status": "ok",
                "rationale_codes": ["missing_required_citation"],
            },
            {
                "label": "NEI",
                "label_4way": "underdetermined",
                "execution_status": "failed",
                "rationale_codes": ["d0_d1_conflict"],
            },
        ]
    )
    assert report["rq2_descriptive"]["unaddressed"] == 1
    assert report["rq2_descriptive"]["underdetermined"] == 1
    assert report["rationale_codes"]["d0_d1_conflict"] == 1
