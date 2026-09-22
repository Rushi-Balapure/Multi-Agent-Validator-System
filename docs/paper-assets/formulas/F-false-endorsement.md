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
- The comparison table is [v_vs_b2_false_endorsement.md](../tables/v_vs_b2_false_endorsement.md). The B2 column cites the live development run; the V column cites the offline fixture-report dry-run `validator-v-development-s0-n3-d5cecb97c55b`. Synthetic fixture claim ids use the evaluation smoke gold map (not `--join-gold development`). `src/evaluation/bootstrap.py` stores the 2000-resample plan and does not emit an interval until paired same-claim-id V and B2 predictions exist.
