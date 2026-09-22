# Graphs

Phase-3 figure drafts generated from checked-in prediction/metrics files only (`python -m evaluation.phase3_figures`).

| Figure | Files | Source run_ids |
| --- | --- | --- |
| FE bar compare (V cited-D0 vs B2 live) | `fe_bar_v_vs_b2.svg` / `.png` / `.meta.json` | `validator-v-gather-development-s0-n20-3c856362819b`, `same-evidence-b2-development-s0-n20-dac855c4e2ae` |
| V cited-D0 label histogram | `v_gather_label_histogram.svg` / `.png` / `.meta.json` | `validator-v-gather-development-s0-n20-3c856362819b` |
| V cited-D0 execution status | `v_gather_cited_d0_status.svg` / `.png` / `.meta.json` | `validator-v-gather-development-s0-n20-3c856362819b` |
| V gather fail-closed status (#23 history) | `v_gather_fail_closed_status.svg` / `.png` / `.meta.json` | `validator-v-gather-development-s0-n20-90129d9056fd` |

Cited-D0 V FE rates are scored (`n_scored=19`, `n_skipped_not_ok=1`). Fail-closed tables under `docs/paper-assets/tables/validator_v_gather/` remain comparison history and are not overwritten.
