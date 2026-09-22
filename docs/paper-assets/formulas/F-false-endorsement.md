# F-false-endorsement — False endorsement rate

**Plan cite:** Research plan §11; primary preregistered comparison V vs B2.  
**Every table cell using this metric must cite `run_id` + this formula id.**

## Definition (primary denominator)

\[
\mathrm{FE}_{\text{gold-nonsup}} = \frac{\#\{\hat{y}=\text{supported} \land y \neq \text{supported}\}}{\#\{y \neq \text{supported}\}}
\]

## Supporting denominator (always report both)

\[
\mathrm{FE}_{\text{pred-sup}} = \frac{\#\{\hat{y}=\text{supported} \land y \neq \text{supported}\}}{\#\{\hat{y}=\text{supported}\}}
\]

## Notes

- Failures / abstentions are not counted as supported predictions.
- Bootstrap by question family (2000 resamples default); report 95% CI.
- The comparison table is [v_vs_b2_false_endorsement.md](../tables/v_vs_b2_false_endorsement.md). The B2 column cites the live development run `same-evidence-b2-development-s0-n20-dac855c4e2ae`. The V column cites Phase-3 cited-D0 gather live `validator-v-gather-development-s0-n20-3c856362819b` on the same 20 claim ids (`n_scored=19`, `n_skipped_not_ok=1`). Both FE denominators are reported from scored rows only. Fail-closed gather (#23) under `tables/validator_v_gather/` (`validator-v-gather-development-s0-n20-90129d9056fd`, `n_skipped_not_ok=20`, FE N/A) is kept as comparison history and is not overwritten. The offline fixture-report dry-run under `tables/validator_v/` remains available via `--paper-table-fixture-v`. `src/evaluation/bootstrap.py` stores the 2000-resample plan and does not emit an interval until paired same-claim-id V and B2 predictions are both fully scorable.
