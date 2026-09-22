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
