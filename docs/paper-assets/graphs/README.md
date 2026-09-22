# Graphs

Phase-3 figure drafts generated from checked-in prediction/metrics files only (`python -m evaluation.phase3_figures`).

| Figure | Files | Source run_ids |
| --- | --- | --- |
| FE bar compare (V gather vs B2 live) | `fe_bar_v_vs_b2.svg` / `.png` / `.meta.json` | `validator-v-gather-development-s0-n20-90129d9056fd`, `same-evidence-b2-development-s0-n20-dac855c4e2ae` |
| V gather label histogram | `v_gather_label_histogram.svg` / `.png` / `.meta.json` | `validator-v-gather-development-s0-n20-90129d9056fd` |
| V gather fail-closed status | `v_gather_fail_closed_status.svg` / `.png` / `.meta.json` | `validator-v-gather-development-s0-n20-90129d9056fd` |

V FE rates are N/A in the bar chart: every gather row is `execution_status=failed` (`n_skipped_not_ok=20`). No invented SUPPORT rates.
