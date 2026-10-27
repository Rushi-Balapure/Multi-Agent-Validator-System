# Results (primary = frozen-configuration 2026-09-25 run)

Primary development artifacts: `artifacts/same_evidence_b2_dev300` and
`artifacts/validator_v_dev300` (config hash `c3d7773f7287…`, the hash locked
in `docs/freeze.json`). Held-out: `artifacts/held_out/`. The 2026-10-20
retry re-run lives under `artifacts/api/dev300/` and is a second run, not
the primary.

Gold mix on the 300-claim development sample: SUPPORT 117, CONTRADICT 62,
NEI 121.

## Primary (RQ1)

Exact McNemar on gold non-support discordant pairs (B2 endorses and V does
not, versus the reverse):

| Model | Run | n paired | non-supp. | B2 only | V only | McNemar p | ΔFE [95% CI] |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GPT-6 Luna | development (frozen) | 268 | 161 | 2 | 0 | 0.50 | −0.012 [−0.031, 0.000] |
| GPT-6 Luna | development (2026-10-20 re-run) | 300 | 183 | 2 | 0 | 0.50 | −0.011 [−0.029, 0.000] |
| GPT-6 Luna | held-out | 262 | 156 | 2 | 0 | 0.50 | −0.013 [−0.033, 0.000] |
| MiniMax M3.1 Flash | development | 300 | 183 | 5 | 2 | 0.45 | −0.016 [−0.046, 0.011] |

**Decision:** inconclusive. V is more conservative (zero or near-zero false
endorsement, lower SUPPORT recall and F1). The comparison is underpowered
(two discordant events on Luna). Independent retrieval's unique yield is 0
on this corpus, so the motivating “repair a wrong citation” mechanism
cannot occur.

## Class trade-off (frozen Luna development)

| Method | n scored | micro-F1 | FE | SUPPORT R | fail-closed |
| --- | --- | --- | --- | --- | --- |
| B2 | 300 | 0.747 | 0.011 | 0.530 | 0 |
| V | 268 | 0.675 | 0.000 | 0.383 | 32 |
| V-D1 (derived) | 268 | 0.743 | 0.019 | 0.598 | 32 |

V misses 66 supported claims and 19 contradicted ones. Held-out V-D1 FE is
0.032 against B2 0.017.

## Run-to-run

B2 flipped 26/300 labels (9%) between the frozen run and the 2026-10-20
re-run; V flipped 14/268 previously-ok labels (5%).
