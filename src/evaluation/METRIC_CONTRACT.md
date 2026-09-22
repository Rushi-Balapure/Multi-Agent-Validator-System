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

## Scoring B2 predictions

`PYTHONPATH=src python -m evaluation.score_predictions` reads a same-evidence `predictions.jsonl` (`claim_id`, predicted `label` in `SUPPORT` / `REFUTE` / `NEI`, optional `label_gold`). It writes metrics JSON. Pass `--join-gold development` to copy claim labels from `data.scifact_loader.load_split` when the artifact has none (empty evidence → NEI; uniform `CONTRADICT` is scored as `REFUTE`; mixed native labels are refused). Each metric includes `run_id` (CLI `--run-id`, else sidecar `run.run_id`) and a formula id:

- Per-class, micro, and macro precision / recall / F1 use `F-native-scifact`. This is label classification only. It is not four-way macro-F1.
- False endorsement uses `F-false-endorsement`. On this label space the endorsement class is `SUPPORT` (false-support rate). Both denominators are reported. `CONTRADICT` gold counts as `REFUTE`.

The scorer does not join the corpus. Rows without gold are skipped. The paper stub is `docs/paper-assets/tables/b2_live_vs_mock.md`. Live artifacts are not in-repo; that note has the command to score them once Baseline drops `artifacts/same_evidence_b2/predictions.jsonl` and `run.json`.

## V versus B2 harness

`PYTHONPATH=src python -m evaluation.harness` compares method_id `B2` and optional `V` on `F-false-endorsement` (both denominators). The method_id enum is `B2` and `V` only. V predictions must use the same claim ids as the B2 prediction rows. A missing or empty V file leaves the V cell pending (`—` in the table). The harness does not copy B2 rates into that cell.

The paper table is `docs/paper-assets/tables/v_vs_b2_false_endorsement.md`. Its B2 column is the checked-in live report `docs/paper-assets/tables/b2_live_n20_metrics.json` (run `same-evidence-b2-development-s0-n20-dac855c4e2ae`). The V column is the offline Stack V fixture-report dry-run `validator-v-development-s0-n3-d5cecb97c55b` (`docs/paper-assets/tables/validator_v/predictions.jsonl` + `run.json`). Those synthetic e2e claim ids are not in the locked development split, so scoring attaches `src/evaluation/fixtures/v_fixture_report_gold.json` rather than `--join-gold development`. Held-out run ids remain placeholders. Regenerating the filled table:

```bash
PYTHONPATH=src python -m evaluation.harness \
  --paper-table \
  --v-metrics-output docs/paper-assets/tables/validator_v/v_dry_run_metrics.json \
  --output docs/paper-assets/tables/v_vs_b2_false_endorsement.md
```

Pending-only regeneration (omit V artifacts):

```bash
PYTHONPATH=src python -m evaluation.harness \
  --output docs/paper-assets/tables/v_vs_b2_false_endorsement.md
```

## Bootstrap-by-family timers

`evaluation.bootstrap.BootstrapByFamilyConfig` stores the contract plan: question family by default, claim family as the other cluster key, `n_resamples=2000`, 95% interval, formula `F-false-endorsement`, methods `B2` and `V`. `describe_bootstrap_timer` returns that plan with `interval=None`. `bootstrap_by_family` raises `NotImplementedError` until V predictions exist. It does not draw resamples and it does not return a confidence interval.

## Latency and tokens on Run

`F-latency-cost` needs median and p95 latency, warm versus cold cache, and token totals. Corpus Lock's `Run` has `timestamps` and `tokens` only. The gap is written in `docs/paper-assets/run_latency_token_contract.md` for Corpus Lock and Arch Lead. Eval Forge does not fork the Run schema and does not invent latency or token totals.
