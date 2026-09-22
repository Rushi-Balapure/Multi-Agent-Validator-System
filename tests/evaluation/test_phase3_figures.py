"""Phase-3 figures come only from checked-in prediction/metrics files."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.phase3_figures import main

ROOT = Path(__file__).resolve().parents[2]
GRAPHS = ROOT / "docs" / "paper-assets" / "graphs"
V_CITED_D0_RUN = "validator-v-gather-development-s0-n20-3c856362819b"
V_FAIL_CLOSED_RUN = "validator-v-gather-development-s0-n20-90129d9056fd"
B2_RUN = "same-evidence-b2-development-s0-n20-dac855c4e2ae"


def test_phase3_figures_cite_saved_run_ids(tmp_path: Path):
    out = tmp_path / "graphs"
    main(["--out-dir", str(out)])
    fe_meta = json.loads((out / "fe_bar_v_vs_b2.meta.json").read_text(encoding="utf-8"))
    assert fe_meta["b2_run_id"] == B2_RUN
    assert fe_meta["v_run_id"] == V_CITED_D0_RUN
    assert fe_meta["v_fe_rates"] is not None
    assert fe_meta["v_fe_rates"]["false_endorsement_gold_nonsup"] == 0.0625
    assert fe_meta["v_fe_rates"]["false_endorsement_pred_sup"] == 1.0
    assert fe_meta["v_n_skipped_not_ok"] == 1
    assert fe_meta["v_n_scored"] == 19
    assert (out / "fe_bar_v_vs_b2.svg").is_file()
    assert (out / "fe_bar_v_vs_b2.png").is_file()
    hist = json.loads((out / "v_gather_label_histogram.meta.json").read_text(encoding="utf-8"))
    assert hist["v_run_id"] == V_CITED_D0_RUN
    assert hist["counts_by_label"] == {"NEI": 19, "SUPPORT": 1}
    status = json.loads(
        (out / "v_gather_cited_d0_status.meta.json").read_text(encoding="utf-8")
    )
    assert status["counts_by_execution_status"] == {"failed": 1, "ok": 19}
    assert status["n_skipped_not_ok"] == 1
    fc = json.loads(
        (out / "v_gather_fail_closed_status.meta.json").read_text(encoding="utf-8")
    )
    assert fc["v_run_id"] == V_FAIL_CLOSED_RUN
    assert fc["counts_by_execution_status"] == {"failed": 20}


def test_checked_in_graphs_meta_matches_cited_d0_run():
    meta = json.loads((GRAPHS / "fe_bar_v_vs_b2.meta.json").read_text(encoding="utf-8"))
    assert meta["v_run_id"] == V_CITED_D0_RUN
    assert meta["b2_run_id"] == B2_RUN
    assert meta["v_fe_rates"] is not None
    assert meta["v_n_skipped_not_ok"] == 1
    assert meta["v_n_scored"] == 19
