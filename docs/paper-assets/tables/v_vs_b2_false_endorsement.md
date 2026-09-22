# V vs B2 false endorsement

Primary comparison for method_id `V` versus `B2` on [F-false-endorsement](../formulas/F-false-endorsement.md). Both denominators are reported. `SUPPORT` is the endorsement class on the SciFact label space (`scifact_SUPPORT_REFUTE_NEI`).

V and B2 share the same claim ids (paired claim set). FE rates come from `evaluation.score_predictions` on each side.

The B2 column is the checked-in live development run `same-evidence-b2-development-s0-n20-dac855c4e2ae` (n scored = 20), the same live column as [b2_live_vs_mock.md](b2_live_vs_mock.md). The V column is cited-D0 gather run `validator-v-gather-development-s0-n20-3c856362819b` (n scored = 19, n_skipped_not_ok = 1). Claim ids match the B2 live set (paired claim alignment). Held-out run ids below are placeholders for the preregistered comparison.

B2 source: `docs/paper-assets/tables/b2_live_n20_metrics.json`.

- formula_id: `F-false-endorsement`
- notes: `docs/paper-assets/formulas/F-false-endorsement.md`
- B2 run_id: `same-evidence-b2-development-s0-n20-dac855c4e2ae`
- V run_id: `validator-v-gather-development-s0-n20-3c856362819b`
- Held-out run_id placeholders, not scored in this table: B2 `<B2 held-out run_id>`, V `<V held-out run_id>`
- V predictions: `docs/paper-assets/tables/validator_v_gather_cited_d0/predictions.jsonl`
- V run sidecar: `docs/paper-assets/tables/validator_v_gather_cited_d0/run.json`
- V gold source: `data.scifact_loader.load_split:development`
- paired claim ids (n=20): `scifact:0`, `scifact:10`, `scifact:11`, `scifact:12`, `scifact:14`, `scifact:15`, `scifact:17`, `scifact:18`, `scifact:19`, `scifact:2`, `scifact:20`, `scifact:21`, `scifact:22`, `scifact:24`, `scifact:25`, `scifact:26`, `scifact:27`, `scifact:4`, `scifact:6`, `scifact:9`
- V n_rows: `20`
- V n_scored: `19`
- V n_skipped_not_ok: `1`
- V n_skipped_unlabeled: `0`
- V B2 sidecar (live): `docs/paper-assets/tables/b2_live_n20_metrics.json` (run `same-evidence-b2-development-s0-n20-dac855c4e2ae`)

Comparison history (facts only): fail-closed gather (#23) under `docs/paper-assets/tables/validator_v_gather/` (`validator-v-gather-development-s0-n20-90129d9056fd`) had `n_skipped_not_ok=20` / `n_scored=0` (FE N/A). Cited-D0 gather (#26) under `docs/paper-assets/tables/validator_v_gather_cited_d0/` (`validator-v-gather-development-s0-n20-3c856362819b`) has `n_skipped_not_ok=1` / `n_scored=19`. The fail-closed set is kept for comparison and is not overwritten.

| Metric | formula_id | B2 (`same-evidence-b2-development-s0-n20-dac855c4e2ae`) | V (`validator-v-gather-development-s0-n20-3c856362819b`) |
| --- | --- | --- | --- |
| run_id | — | `same-evidence-b2-development-s0-n20-dac855c4e2ae` | `validator-v-gather-development-s0-n20-3c856362819b` |
| false endorsement, gold non-supported denominator | `F-false-endorsement` | 0.17647058823529413 | 0.0625 |
| false endorsement, predicted-supported denominator | `F-false-endorsement` | 1.0 | 1.0 |
| n false endorsements | `F-false-endorsement` | 3 | 1 |
| n gold non-supported | `F-false-endorsement` | 17 | 16 |
| n predicted supported | `F-false-endorsement` | 3 | 1 |
| n_skipped_not_ok | — | 0 | 1 |
| n_scored | — | 20 | 19 |

Bootstrap by question family (claim family is the other cluster key) is configured at 2000 resamples in `src/evaluation/bootstrap.py`. That scaffold does not emit a confidence interval. Latency and token totals stay on the Run record; see [the Run field note](../run_latency_token_contract.md).

**Next contract (not implemented in this MR):** a separate D1-mapped label column scored without remapping fail-closed D0 rows into SUPPORT rates. Do not silently remap `execution_status=failed` to scorables. Cited-D0 gather (non-gold proposer citations as D0) is the scored V column in this table; the fail-closed set under `validator_v_gather/` remains comparison history.
