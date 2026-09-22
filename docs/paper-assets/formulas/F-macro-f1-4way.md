# F-macro-f1-4way — Four-way macro-F1

**Plan cite:** Research plan §11 Verification quality.  
**Every table cell using this metric must cite `run_id` + this formula id.**

## Definition

Let classes \(C = \{\text{supported}, \text{refuted}, \text{unaddressed}, \text{underdetermined}\}\).

For each class \(c \in C\):

\[
P_c = \frac{\mathrm{TP}_c}{\mathrm{TP}_c + \mathrm{FP}_c}, \quad
R_c = \frac{\mathrm{TP}_c}{\mathrm{TP}_c + \mathrm{FN}_c}, \quad
F1_c = \frac{2 P_c R_c}{P_c + R_c}
\]

(with \(F1_c = 0\) if \(P_c + R_c = 0\)).

\[
\mathrm{macro\text{-}F1} = \frac{1}{|C|} \sum_{c \in C} F1_c
\]

## Notes

- Custom four-way gold only. Do not compute this on native SciFact three-way labels without an explicit coarse-mapping experiment (collapse unaddressed+underdetermined → insufficient information) labeled as supplementary.
