# Results (dev-300 gpt-6-luna)

Sample: `data/manifests/dev300_seed42.json` (seed 42). Gold mix: SUPPORT 117,
CONTRADICT 62, NEI 121. Model: gpt-6-luna. 226 cited-document families.
Paired bootstrap 2000 resamples on 268 claims (32 V rows fail-closed).

## Primary (RQ1)

| Method | n scored | micro-F1 | macro-F1 | FE gold-nonsup | SUPPORT recall | fail-closed |
| --- | --- | --- | --- | --- | --- | --- |
| B2 | 300 | 0.747 | 0.755 | 0.011 [0.000, 0.031] | 0.530 | 0 |
| V | 268 | 0.675 | 0.673 | 0.000 [0.000, 0.000] | 0.383 | 32 |

Paired FE difference V−B2: −0.012 [−0.031, 0.000], excludes_zero=false, p=0.46.

**Decision:** null primary result. V is more conservative (zero false
endorsements, lower recall and F1) but the FE interval includes no
difference. Report as a negative-results / no-significant-gain paper on
the same tables.

## 2x2 and references

| Cell | micro-F1 | FE gold-nonsup | SUPPORT recall |
| --- | --- | --- | --- |
| B0 prior knowledge | 0.557 | 0.448 | 0.872 |
| B1 D0 claim-visible | 0.840 | 0.049 | 0.838 |
| B2 D0 evidence-first | 0.747 | 0.011 | 0.530 |
| B3 D1 claim-visible | 0.790 | 0.055 | 0.795 |
| V-D1 D1 only | 0.743 | 0.019 | 0.598 |
| V reconciled | 0.675 | 0.000 | 0.383 |
| O gold rationales | 0.857 | 0.016 | 0.735 |

B2@k matched budget: V uses 7462 tokens/claim vs B2 1209, so k=7. Extra
self-consistency seeds were not spent after the null primary.

## RQ2 descriptive

V predicted NEI on 225 claims: 60 unaddressed, 165 underdetermined.
Rationale codes: labels_agree 163, d0_d1_conflict 137.

## Calibration (B1 verbalized confidence)

n=300, temperature=1.8, Brier=0.256, NLL=0.492, ECE=0.060.

## Held-out 300 (frozen, one run)

219 cited-document families. 262 paired claims (38 V fail-closed).

| Method | n scored | micro-F1 | FE gold-nonsup | SUPPORT recall | fail-closed |
| --- | --- | --- | --- | --- | --- |
| B2 | 300 | 0.760 | 0.017 (paired 0.013 [0.000, 0.033]) | 0.581 | 0 |
| V | 262 | 0.618 | 0.000 [0.000, 0.000] | 0.368 | 38 |

Paired FE difference V−B2: −0.013 [−0.033, 0.000], excludes_zero=false, p=0.44.

The held-out run confirms the development null: V remains fail-closed and
zero-FE, B2 is higher-F1, and the primary interval still includes no
difference.
