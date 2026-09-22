# V vs B2 false endorsement

Primary comparison for method_id `V` versus `B2` on [F-false-endorsement](../formulas/F-false-endorsement.md). Both denominators are reported. `SUPPORT` is the endorsement class on the SciFact label space (`scifact_SUPPORT_REFUTE_NEI`).

V predictions are present on the same claim ids as B2, but every V row was skipped as not-ok (fail-closed D0). FE cells are `N/A` (not 0.0). Rates are not invented from reconciled NEI labels.

The B2 column is the checked-in live development run `same-evidence-b2-development-s0-n20-dac855c4e2ae` (n scored = 20), the same live column as [b2_live_vs_mock.md](b2_live_vs_mock.md). The V column is gather run `validator-v-gather-development-s0-n20-90129d9056fd` (n scored = 0, n_skipped_not_ok = 20). Claim ids match the B2 live set (paired claim alignment). Held-out run ids below are placeholders for the preregistered comparison.

B2 source: `docs/paper-assets/tables/b2_live_n20_metrics.json`.

- formula_id: `F-false-endorsement`
- notes: `docs/paper-assets/formulas/F-false-endorsement.md`
- B2 run_id: `same-evidence-b2-development-s0-n20-dac855c4e2ae`
- V run_id: `validator-v-gather-development-s0-n20-90129d9056fd` (skipped_not_ok)
- Held-out run_id placeholders, not scored in this table: B2 `<B2 held-out run_id>`, V `<V held-out run_id>`
- V predictions: `docs/paper-assets/tables/validator_v_gather/predictions.jsonl`
- V run sidecar: `docs/paper-assets/tables/validator_v_gather/run.json`
- paired claim ids (n=20): `scifact:0`, `scifact:10`, `scifact:11`, `scifact:12`, `scifact:14`, `scifact:15`, `scifact:17`, `scifact:18`, `scifact:19`, `scifact:2`, `scifact:20`, `scifact:21`, `scifact:22`, `scifact:24`, `scifact:25`, `scifact:26`, `scifact:27`, `scifact:4`, `scifact:6`, `scifact:9`
- V n_rows: `20`
- V n_scored: `0`
- V n_skipped_not_ok: `20`
- V n_skipped_unlabeled: `0`
- V B2 sidecar (live): `docs/paper-assets/tables/b2_live_n20_metrics.json` (run `same-evidence-b2-development-s0-n20-dac855c4e2ae`)

V gather fail-closed D0: every prediction row has execution_status not ok (20/20 skipped as n_skipped_not_ok). Gather does not load gold D0 citations, so the auditor fail-closes and the reconciled label maps to underdetermined/NEI. F-false-endorsement rates are N/A — not 0.0 — because no row entered the FE denominators. Do not remap failed rows to scorables.

| Metric | formula_id | B2 (`same-evidence-b2-development-s0-n20-dac855c4e2ae`) | V (`validator-v-gather-development-s0-n20-90129d9056fd`) |
| --- | --- | --- | --- |
| run_id | — | `same-evidence-b2-development-s0-n20-dac855c4e2ae` | `validator-v-gather-development-s0-n20-90129d9056fd` (skipped) |
| false endorsement, gold non-supported denominator | `F-false-endorsement` | 0.17647058823529413 | N/A |
| false endorsement, predicted-supported denominator | `F-false-endorsement` | 1.0 | N/A |
| n false endorsements | `F-false-endorsement` | 3 | N/A |
| n gold non-supported | `F-false-endorsement` | 17 | N/A |
| n predicted supported | `F-false-endorsement` | 3 | N/A |
| n_skipped_not_ok | — | 0 | 20 |
| n_scored | — | 20 | 0 |

Bootstrap by question family (claim family is the other cluster key) is configured at 2000 resamples in `src/evaluation/bootstrap.py`. That scaffold does not emit a confidence interval. Latency and token totals stay on the Run record; see [the Run field note](../run_latency_token_contract.md).

**Next contract (not implemented in this MR):** either (a) a separate D1-mapped label column scored without remapping fail-closed D0 rows into SUPPORT rates, or (b) a Judge slice that attaches non-gold proposer citations for D0 so gather rows can be execution-ok without inventing gold D0. Do not silently remap `execution_status=failed` to scorables.
