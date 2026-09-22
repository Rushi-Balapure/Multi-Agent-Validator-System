# F-brier-multi — Multiclass Brier score

**Plan cite:** Research plan §11 Calibration.

\[
\mathrm{Brier} = \frac{1}{N} \sum_{i=1}^{N} \sum_{c \in C} \bigl(p_{i,c} - \mathbf{1}[y_i = c]\bigr)^2
\]

Report also NLL, reliability plots, and ECE with stated bin settings and calibration sample size. Fit temperature on a held-out calibration split only — never on the test set.
