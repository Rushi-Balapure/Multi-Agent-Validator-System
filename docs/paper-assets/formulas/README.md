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

No formula notes yet. Do not treat these names as measured results.
