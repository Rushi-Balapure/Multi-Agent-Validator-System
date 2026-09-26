# T1 Held-out 300 (frozen, one run)

Primary metric is V versus B2 false endorsement on gold non-support.
Intervals are paired cluster bootstrap (2000 resamples) over cited-document families.

| Method | n | micro-F1 | macro-F1 | FE gold-nonsup | SUPPORT recall | fail-closed |
| --- | --- | --- | --- | --- | --- | --- |
| B2 | 300 | 0.760 | 0.765 | 0.017 | 0.581 | 0 |
| V | 262 | 0.618 | 0.599 | 0.000 | 0.368 | 38 |

Paired FE difference (V − B2): -0.013 [-0.033, 0.000], excludes_zero=false, p=0.44.
Families: 219. Paired claims: 262. Dropped fail-closed: 38.
