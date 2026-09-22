# Formulas

Reference notes for cited paper metrics go in this directory.

Planned notes, taken from the research plan (metrics and statistics, and the retrieval protocol):

- Native SciFact support / refute / evidence scores
- Four-way macro-F1 on custom labels
- False endorsement (predicted supported among gold non-supported, and wrong supported predictions among all supported predictions)
- Evidence acquisition: Recall@k and Precision@k
- Multiclass Brier score: mean over items of the sum over classes of `(p_class - indicator)^2`
- Negative log-likelihood and expected calibration error (bin settings recorded with the note)
- Selective use: error among accepted claims versus fraction accepted
- Proposed dense-plus-BM25 fusion score, if that comparison is run: sum of `1 / (60 + rank)` across lists

Landed metric-contract notes (definitions only; not measured results):

- [F-macro-f1-4way](F-macro-f1-4way.md) — four-way macro-F1
- [F-native-scifact](F-native-scifact.md) — native SciFact scores
- [F-false-endorsement](F-false-endorsement.md) — false endorsement
- [F-claim-coverage](F-claim-coverage.md) — claim coverage
- [F-recall-at-k](F-recall-at-k.md) — evidence Recall@k
- [F-brier-multi](F-brier-multi.md) — multiclass Brier (NLL and ECE recorded with this note)
- [F-selective-error](F-selective-error.md) — selective-use error
- [F-latency-cost](F-latency-cost.md) — latency and cost

Do not treat these names as measured results.
