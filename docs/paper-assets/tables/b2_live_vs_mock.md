# B2 live vs dry-run mock

**Live column:** development-split B2, n=20, `inference_mode=live`, `model_invoked=true`.  
**run_id:** `same-evidence-b2-development-s0-n20-dac855c4e2ae` (sidecar `run.run_id`). Every live number below is that run.  
**Mock column:** placeholder. The hand-computed fixture `fixture-b2-score-001` (`src/evaluation/fixtures/b2_predictions.jsonl`) is a separate 10-row check. It is not a dry-run of these 20 claims, and a development-split mock score is not filled in here.

**Label space:** `scifact_SUPPORT_REFUTE_NEI`. Predictions had no gold. Labels were copied from `data.scifact_loader.load_split("development")`: empty evidence → NEI (16 claims); uniform `SUPPORT` kept (3 claims); uniform `CONTRADICT` kept and scored as `REFUTE` (1 claim, `scifact:2`). Mixed native labels were not present. This is not four-way gold and not the held-out split.

**Not this table:** [F-macro-f1-4way](../formulas/F-macro-f1-4way.md).

Formula notes:

- Label precision / recall / F1 (per class, micro, macro): [F-native-scifact](../formulas/F-native-scifact.md). Label-only classification. These rows have no sentence rationales, so this is not the community evidence-selection score.
- False endorsement / false-support rate (both denominators): [F-false-endorsement](../formulas/F-false-endorsement.md)

`SUPPORT` is the endorsement class. Exact JSON, including per-claim gold: [b2_live_n20_metrics.json](b2_live_n20_metrics.json). `artifacts/` is gitignored, so that file is the checked-in score.

| Metric | formula_id | B2 dry-run mock (placeholder) | B2 live (`same-evidence-b2-development-s0-n20-dac855c4e2ae`) |
| --- | --- | --- | --- |
| run_id | — | placeholder | `same-evidence-b2-development-s0-n20-dac855c4e2ae` |
| SUPPORT precision | `F-native-scifact` | placeholder | 0 |
| SUPPORT recall | `F-native-scifact` | placeholder | 0 |
| SUPPORT F1 | `F-native-scifact` | placeholder | 0 |
| REFUTE precision | `F-native-scifact` | placeholder | 0.25 |
| REFUTE recall | `F-native-scifact` | placeholder | 1 |
| REFUTE F1 | `F-native-scifact` | placeholder | 0.4 |
| NEI precision | `F-native-scifact` | placeholder | 0.8461538461538461 |
| NEI recall | `F-native-scifact` | placeholder | 0.6875 |
| NEI F1 | `F-native-scifact` | placeholder | 0.7586206896551724 |
| micro F1 | `F-native-scifact` | placeholder | 0.6 |
| macro F1 | `F-native-scifact` | placeholder | 0.3862068965517242 |
| false endorsement, gold non-supported denominator (false-support rate) | `F-false-endorsement` | placeholder | 0.17647058823529413 |
| false endorsement, predicted-supported denominator | `F-false-endorsement` | placeholder | 1 |

Live confusion counts (gold, pred), same run_id, formula `F-native-scifact`: SUPPORT tp/fp/fn = 0/3/3; REFUTE 1/3/0; NEI 11/2/5. False endorsement (`F-false-endorsement`): 3 false SUPPORT predictions, 17 gold non-SUPPORT, 3 predicted SUPPORT.

## Command

Predictions do not include gold. `--join-gold development` reads the locked loader. The sidecar `corpus_hash` must match `data/pins/scifact/PIN.json`.

```bash
PYTHONPATH=src python -m evaluation.score_predictions \
  --predictions artifacts/same_evidence_b2/predictions.jsonl \
  --run-sidecar artifacts/same_evidence_b2/run.json \
  --join-gold development \
  --output docs/paper-assets/tables/b2_live_n20_metrics.json
```

The fixture check, which is not this live run and not a dry-run of the same 20 claims:

```bash
PYTHONPATH=src python -m evaluation.score_predictions \
  --predictions src/evaluation/fixtures/b2_predictions.jsonl \
  --run-id fixture-b2-score-001 \
  --output /tmp/b2_fixture_metrics.json
```
