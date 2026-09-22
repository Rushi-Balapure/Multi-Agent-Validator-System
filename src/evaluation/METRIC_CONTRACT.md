# Metric contract (Eval Forge)

**Status:** ready for MR after scaffold merges to main.  
**Approved by Arch Lead (2026-09-22):** paths, method_id, schema ownership.

## Ownership

| Concern | Path | Owner |
|---------|------|--------|
| Shared records (Run, Claim, Evidence, Judgment, Report verdict, prediction fields) | `src/validator/schemas.py` (or `schemas/` if Corpus Lock prefers) | Corpus Lock + Arch Lead |
| Metric formula registry, scorers, adapters, bootstrap | `src/evaluation/` | Eval Forge |
| Paper graphs / formula notes | `docs/paper-assets/` | Eval Forge |

Eval Forge **imports** shared prediction/verdict types. It does **not** fork them. Missing fields → tiny contract note to Corpus Lock.

## method_id (frozen for this MR)

- `B2` — same-evidence baseline
- `V` — independent retrieval + staged judge

Do not invent ablation method_ids in this MR.

## Formula registry

| Formula id | Name | Notes file |
|------------|------|------------|
| `F-macro-f1-4way` | Four-way macro-F1 | `docs/paper-assets/formulas/F-macro-f1-4way.md` |
| `F-native-scifact` | Native SciFact scores | `docs/paper-assets/formulas/F-native-scifact.md` |
| `F-false-endorsement` | False endorsement | `docs/paper-assets/formulas/F-false-endorsement.md` |
| `F-claim-coverage` | Claim coverage | `docs/paper-assets/formulas/F-claim-coverage.md` |
| `F-recall-at-k` | Evidence Recall@k | `docs/paper-assets/formulas/F-recall-at-k.md` |
| `F-brier-multi` | Multiclass Brier | `docs/paper-assets/formulas/F-brier-multi.md` |
| `F-selective-error` | Selective-use error | `docs/paper-assets/formulas/F-selective-error.md` |
| `F-latency-cost` | Latency / cost | `docs/paper-assets/formulas/F-latency-cost.md` |

## Primary comparison

Preregistered: **V vs B2** on `F-false-endorsement` (custom held-out). Bootstrap by question family, 2000 resamples, 95% CI.

## Prediction artifact fields (expected from shared schemas)

Consumed fields (must exist on shared types; do not redefine here):  
`run_id`, `method_id`, `question_id`, `claim_id`, `split`, `seed`, `model_id`, `model_revision`, `prompt_hash`, `corpus_hash`, `config_hash`, `label_pred`, `label_gold`, `evidence_scope`, `execution_status`, `probabilities`, `failure_reason`.

## Anti-jobs

No corpus-split edits. No baseline/retrieval/judge code changes to chase scores. No test-set calibration fitting. No outside-evidence relabeling called “native SciFact.”
