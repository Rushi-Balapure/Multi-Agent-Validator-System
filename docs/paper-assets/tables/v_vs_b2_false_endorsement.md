# V vs B2 false endorsement

Primary comparison for method_id `V` versus `B2` on [F-false-endorsement](../formulas/F-false-endorsement.md). Both denominators are reported. `SUPPORT` is the endorsement class on the SciFact label space (`scifact_SUPPORT_REFUTE_NEI`).

V is scored from its own predictions (independent of the B2 claim set). Rates come from `evaluation.score_predictions` on that run_id. This is not yet the paired same-claim-id comparison.

The B2 column is the checked-in live development run `same-evidence-b2-development-s0-n20-dac855c4e2ae` (n scored = 20), the same live column as [b2_live_vs_mock.md](b2_live_vs_mock.md). The V column is run `validator-v-development-s0-n3-d5cecb97c55b` (n scored = 2). Held-out run ids below are placeholders for the preregistered comparison.

B2 source: `docs/paper-assets/tables/b2_live_n20_metrics.json`.

- formula_id: `F-false-endorsement`
- notes: `docs/paper-assets/formulas/F-false-endorsement.md`
- B2 run_id: `same-evidence-b2-development-s0-n20-dac855c4e2ae`
- V run_id: `validator-v-development-s0-n3-d5cecb97c55b`
- Held-out run_id placeholders, not scored in this table: B2 `<B2 held-out run_id>`, V `<V held-out run_id>`
- V predictions: `docs/paper-assets/tables/validator_v/predictions.jsonl`
- V run sidecar: `docs/paper-assets/tables/validator_v/run.json`
- V gold source: `src/evaluation/fixtures/v_fixture_report_gold.json`

| Metric | formula_id | B2 (`same-evidence-b2-development-s0-n20-dac855c4e2ae`) | V (`validator-v-development-s0-n3-d5cecb97c55b`) |
| --- | --- | --- | --- |
| run_id | — | `same-evidence-b2-development-s0-n20-dac855c4e2ae` | `validator-v-development-s0-n3-d5cecb97c55b` |
| false endorsement, gold non-supported denominator | `F-false-endorsement` | 0.17647058823529413 | 0.0 |
| false endorsement, predicted-supported denominator | `F-false-endorsement` | 1.0 | 0.0 |
| n false endorsements | `F-false-endorsement` | 3 | 0 |
| n gold non-supported | `F-false-endorsement` | 17 | 1 |
| n predicted supported | `F-false-endorsement` | 3 | 1 |

Bootstrap by question family (claim family is the other cluster key) is configured at 2000 resamples in `src/evaluation/bootstrap.py`. That scaffold does not emit a confidence interval. Latency and token totals stay on the Run record; see [the Run field note](../run_latency_token_contract.md).
