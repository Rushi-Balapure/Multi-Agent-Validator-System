# V vs B2 false endorsement

Primary comparison for method_id `V` versus `B2` on [F-false-endorsement](../formulas/F-false-endorsement.md). Both denominators are reported. `SUPPORT` is the endorsement class on the SciFact label space (`scifact_SUPPORT_REFUTE_NEI`).

V predictions are missing or empty. V cells are pending. An em dash (`—`) is an absent score. This table does not invent V numbers.

The B2 column is the checked-in live development run `same-evidence-b2-development-s0-n20-dac855c4e2ae` (n scored = 20), the same live column as [b2_live_vs_mock.md](b2_live_vs_mock.md). It is the development live column. Held-out run ids below are placeholders for the preregistered comparison.

B2 source: `docs/paper-assets/tables/b2_live_n20_metrics.json`.

- formula_id: `F-false-endorsement`
- notes: `docs/paper-assets/formulas/F-false-endorsement.md`
- B2 run_id: `same-evidence-b2-development-s0-n20-dac855c4e2ae`
- V run_id: `<V run_id>` (pending)
- Held-out run_id placeholders, not scored in this table: B2 `<B2 held-out run_id>`, V `<V held-out run_id>`

| Metric | formula_id | B2 (`same-evidence-b2-development-s0-n20-dac855c4e2ae`) | V (`<V run_id>`) |
| --- | --- | --- | --- |
| run_id | — | `same-evidence-b2-development-s0-n20-dac855c4e2ae` | pending |
| false endorsement, gold non-supported denominator | `F-false-endorsement` | 0.17647058823529413 | — |
| false endorsement, predicted-supported denominator | `F-false-endorsement` | 1.0 | — |
| n false endorsements | `F-false-endorsement` | 3 | — |
| n gold non-supported | `F-false-endorsement` | 17 | — |
| n predicted supported | `F-false-endorsement` | 3 | — |

Bootstrap by question family (claim family is the other cluster key) is configured at 2000 resamples in `src/evaluation/bootstrap.py`. That scaffold does not emit a confidence interval. Latency and token totals stay on the Run record; see [the Run field note](../run_latency_token_contract.md).
