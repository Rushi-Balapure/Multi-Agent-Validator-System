# Paper assets

This tree holds paper metric graphs and reference mathematical formulas for the research paper.

- [`graphs/`](graphs/) — figure drafts for the paper (metric plots and the architecture diagram).
- [`tables/`](tables/) — result tables. [b2_live_vs_mock](tables/b2_live_vs_mock.md) fills the B2 live development n=20 column from run `same-evidence-b2-development-s0-n20-dac855c4e2ae` ([metrics](tables/b2_live_n20_metrics.json)). The dry-run mock column is still a placeholder. Cells cite [F-native-scifact](formulas/F-native-scifact.md) and [F-false-endorsement](formulas/F-false-endorsement.md). [v_vs_b2_false_endorsement](tables/v_vs_b2_false_endorsement.md) keeps that live B2 column and leaves method `V` pending until V predictions exist.
- [`formulas/`](formulas/) — reference notes for the mathematical definitions of cited metrics. The metric-contract notes are [F-macro-f1-4way](formulas/F-macro-f1-4way.md), [F-native-scifact](formulas/F-native-scifact.md), [F-false-endorsement](formulas/F-false-endorsement.md), [F-claim-coverage](formulas/F-claim-coverage.md), [F-recall-at-k](formulas/F-recall-at-k.md), [F-brier-multi](formulas/F-brier-multi.md), [F-selective-error](formulas/F-selective-error.md), and [F-latency-cost](formulas/F-latency-cost.md).

The live column above is a development-split score, not the preregistered held-out comparison. [Run latency and token fields](run_latency_token_contract.md) are still open with Corpus Lock and Arch Lead; Eval Forge does not invent those totals. Figures and the other formula notes follow the locked experiments in [the implementation plan](../IMPLEMENTATION_PLAN.md). The research scope stays the [two-month research plan](../../Validator_Agent_Two_Month_Research_Plan.pdf).
