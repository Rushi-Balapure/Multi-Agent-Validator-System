# B2 live vs dry-run mock

**Status:** table skeleton. Not a measured result.  
**Label space:** `scifact_SUPPORT_REFUTE_NEI` (B2 predictions). `CONTRADICT` gold is scored as `REFUTE`.  
**Not this table:** [F-macro-f1-4way](../formulas/F-macro-f1-4way.md) is four-way custom labels only. Do not fill these cells with it.

Every cell below must cite the run's `run_id` plus the formula id in that row. Formula notes:

- Label precision / recall / F1 (per class, micro, macro) on `SUPPORT` / `REFUTE` / `NEI`: [F-native-scifact](../formulas/F-native-scifact.md). This is label-only classification. The prediction rows have no sentence rationales, so this is not the community evidence-selection score.
- False endorsement / false-support rate (both denominators): [F-false-endorsement](../formulas/F-false-endorsement.md)

`SUPPORT` is the endorsement class (native counterpart of `supported`). Primary rate is false SUPPORT among gold non-SUPPORT. The second rate is false SUPPORT among predicted SUPPORT.

Live B2 artifacts are not in this repo (`/artifacts/` is gitignored). No live or development-split mock numbers are filled in. The committed check is the hand-computed fixture `src/evaluation/fixtures/b2_predictions.jsonl`, not a paper result.

| Metric | formula_id | B2 dry-run mock (`inference_mode=mock`) | B2 live |
| --- | --- | --- | --- |
| run_id | — | — | — |
| SUPPORT precision | `F-native-scifact` | — | — |
| SUPPORT recall | `F-native-scifact` | — | — |
| SUPPORT F1 | `F-native-scifact` | — | — |
| REFUTE precision | `F-native-scifact` | — | — |
| REFUTE recall | `F-native-scifact` | — | — |
| REFUTE F1 | `F-native-scifact` | — | — |
| NEI precision | `F-native-scifact` | — | — |
| NEI recall | `F-native-scifact` | — | — |
| NEI F1 | `F-native-scifact` | — | — |
| micro F1 | `F-native-scifact` | — | — |
| macro F1 | `F-native-scifact` | — | — |
| false endorsement, gold non-supported denominator (false-support rate) | `F-false-endorsement` | — | — |
| false endorsement, predicted-supported denominator | `F-false-endorsement` | — | — |

## How to fill a column

Baseline's dry-run writes `artifacts/same_evidence_b2/predictions.jsonl` and `artifacts/same_evidence_b2/run.json` with `inference_mode=mock`. A call that reaches the local endpoint currently records `inference_mode=endpoint`. After Baseline renames that mode to `inference_mode=live`, score the live artifact with the same command. Do not mix mock and live rows in one file. Copy `run_id` from the sidecar (`run.run_id`) into the table with each value.

Those prediction rows do not include gold. Add `label_gold` on each row (`SUPPORT`, `REFUTE`, or `NEI`; `CONTRADICT` is accepted as `REFUTE`) before scoring. This command does not read the corpus.

```bash
PYTHONPATH=src python -m evaluation.score_predictions \
  --predictions artifacts/same_evidence_b2/predictions.jsonl \
  --run-sidecar artifacts/same_evidence_b2/run.json \
  --output artifacts/same_evidence_b2/metrics.json
```

`--run-id` overrides the sidecar. The fixture check, which is not a live or dry-run result:

```bash
PYTHONPATH=src python -m evaluation.score_predictions \
  --predictions src/evaluation/fixtures/b2_predictions.jsonl \
  --run-id fixture-b2-score-001 \
  --output /tmp/b2_fixture_metrics.json
```
