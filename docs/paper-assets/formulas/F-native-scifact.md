# F-native-scifact — Native SciFact scores

**Plan cite:** Research plan §11 Verification quality.  
**Every table cell using this metric must cite `run_id` + this formula id.**

## Definition

Official SciFact support / refute / evidence metrics via the community evaluation adapters on the public benchmark split. Keep official three-way labels distinct from custom four-way labels.

## Notes

Three-way insufficient-information labels do not supply gold four-way underdetermined labels. A supplementary coarse mapping (collapse unaddressed + underdetermined → insufficient information) must be labeled as supplementary, never as native.

## Label-only classification

B2 `predictions.jsonl` stores one label per claim (`SUPPORT`, `REFUTE`, or `NEI`) and no sentence rationales. The scorer in `src/evaluation/score_predictions.py` reports per-class, micro, and macro precision / recall / F1 on that label set under this formula id. It does not run the community evidence-selection adapter. `CONTRADICT` gold is scored as `REFUTE`. Do not fill these cells with [F-macro-f1-4way](F-macro-f1-4way.md).
