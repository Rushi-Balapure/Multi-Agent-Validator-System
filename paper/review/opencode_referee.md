# Referee Report

**Paper:** *Multi-Agent Validator System: Independent Evidence for Scientific Claim Verification*

## Summary

The paper proposes a staged LLM pipeline for scientific claim verification: a claim-blind reader, a claim-visible judge over four labels, a citation auditor over the original citations, and a reconciler that reports two evidence scopes separately. It compares the validator (V) against a same-evidence baseline (B2) that reads the original citations through an isolated reader. On SciFact, the headline result is a null: on 300 development claims, B2 has false endorsement (FE) 0.011 and V has 0.000, but V’s SUPPORT recall falls from 0.573 to 0.427; the paired difference is −0.011 [−0.029, 0.000]. A local held-out sample repeats the pattern (B2 FE 0.017 vs V 0.000) but V has 38/300 fail-closed rows and is scored on 262 claims. A MiniMax family comparison is also null (−0.016 [−0.046, 0.011]), and a 30-claim, four-model sweep reports ΔFE = 0.000 in all rows. The paper interprets the result as a reproducible negative finding: independent retrieval is not the bottleneck; reconciliation/abstention is; the cost is withheld support. It also reports cost, calibration for one condition, and an artifact/reproducibility contract.

## Strengths

- The paper is unusually transparent about what it did not do: no human study, no ethics review, prompt-level rather than trained baselines, and a partial MiniMax matrix.
- The reproducibility contract is thoughtful: prediction files, run sidecars, prompt hashes, corpus hashes, freeze records, and generated tables.
- The fail-closed execution semantics are a sensible engineering choice, and the distinction between execution status and scientific verdict is the right principle.
- The paper reports the support-recall cost directly rather than hiding it behind F1.
- Table 7 gives per-class precision/recall/confusion counts, which is more informative than a single aggregate.
- The paper correctly notices that SciFact’s cited-document set contains the annotated evidence, which limits what independent retrieval can add.

These strengths make the paper worth reading, but they do not rescue the central experimental claim.

## Major weaknesses

### 1. The benchmark cannot test the stated hypothesis

**Problem.** The paper motivates the work with the scenario in which “the generator cited the wrong paper” and the checker “cannot notice.” But in SciFact, D0 is not a possibly-wrong generator citation set; it is the gold cited evidence set. The paper admits this in Section 7.6: “every annotated document it finds was also cited by the report: the unique yield is 0.00,” and “In SciFact the cited document set contains the annotated document set, so a retrieval system that searches the same corpus cannot find new gold evidence.” The independent retrieval arm therefore has no annotated evidence to add. The manipulation “searching beyond the supplied citations” is null by construction.

**Why it matters.** The experiment does not test whether independent retrieval repairs bad citations; it tests whether adding redundant retrieval to gold citations changes verdicts. The negative result is largely a property of SciFact’s construction. The abstract’s first sentence (“We test whether searching beyond the supplied citations reduces it”) and the title’s “Independent Evidence” overstate what was tested.

**Evidence.** Section 7.6 and Table 10: unique yield 0.000; annotated documents retrieved that were not cited 0; unjudged rate 0.926; claims with annotated evidence 179. Section 3.1 defines D0 as “the documents the original report cited. These are the generator’s evidence,” but in SciFact these are the benchmark’s evidence documents.

**Concrete fix.** Add a biased-citation condition: replace or perturb D0 with random or contradicting abstracts, then measure whether D1 recovers the gold rationale and reduces false endorsement. Alternatively, use SciFact-Open or live search, where independent retrieval can actually find new evidence. If neither is possible, reframe the claim as “on gold citations, additional retrieval does not help” rather than “searching beyond citations does not help.”

### 2. The V–B2 comparison is a compound treatment, not a matched same-evidence/staging contrast

**Problem.** V’s judge “sees the atomic claim, the sealed reader record, and the evidence passages” (Section 4.1). B2’s compare step receives only “the claim, the neutral question, and the sealed reader record” (Appendix A). B2 never re-reads the passages. V’s D0 arm is a claim-visible auditor; B2’s D0 arm is a claim-blind reader. V also uses three calls per claim at about 2,598 tokens per call, while B2 uses two calls at about 605 tokens per call — roughly 6.4× the token budget — and V may use a second retrieval round. RQ1 says “At a matched inference budget,” but the Limitations admit “No matched-budget control was run.”

**Why it matters.** The comparison confounds evidence scope, reading policy, final-stage evidence access, number of model calls, and compute. The observed conservatism cannot be attributed to staging or independent retrieval. The 2×2 factorial does not fix this because V is not a cell in the factorial, and V-D1 is derived from V predictions rather than run independently.

**Evidence.** Section 4.1 (judge input); Appendix A (compare input); Section 7.7 (3 calls vs 2, 2,598 vs 605 tokens); RQ1 (“matched inference budget”); Limitations (“No matched-budget control was run”); Section 6.2 (“V-D1 … recovered from the V predictions by a mapping step rather than a second model run”).

**Concrete fix.** Give B2 the same passages at compare time and make V’s D0 arm the same claim-blind reader as B2. Run V-D1 independently. Add a compute-matched control — e.g., B2 with self-consistency or an ensemble at 6× tokens — and report it as the primary comparison. The current result may be mostly a compute/abstention effect.

### 3. The “preregistered” primary test is reported on the development sample; the held-out test is incomplete and protocol-deviant

**Problem.** Section 6.4 says: “One primary comparison was preregistered before the held-out run: V versus B2 on false endorsement with the gold non-support denominator.” Section 7.1 says: “Table 3 gives the development results and Table 4 the preregistered paired comparison.” But Table 4 contains only development rows (n=300) for Luna and MiniMax. The held-out result appears only in prose: “The paired difference is −0.013 ([−0.033, 0.000]), again including zero,” with no n and no table row. Table 5 says the held-out V was scored on 262 claims with 38 failures, and Section 5.4 says the held-out run “does not use the retry policy.” Meanwhile, Section 6.1 says the development sample was “used for all development and prompt decisions.”

**Why it matters.** The development sample is not a valid test of a preregistered hypothesis. The only valid test is the held-out sample, which is missing from Table 4, analyzed on 262 rather than 300 claims, and run under a different failure-handling protocol. The abstract’s “43% … 57%” and “1 in 100” are development numbers; the held-out numbers are 36.8% vs 58.1% (scored only) or 31.5% vs 58.1% (all rows). The paper’s headline is therefore not the preregistered test.

**Evidence.** Abstract (“Across 300 development claims … 43% … 57%”); Intro (“On the frozen development sample … −0.011 [−0.029, 0.000]”); Section 6.4; Section 7.1; Table 4; Table 5 (V held-out n=262); Section 5.4.

**Concrete fix.** Add the held-out row to Table 4 with n=262 and the all-rows n=300; report both paired CIs. Explain and justify the no-retry deviation, or rerun the held-out sample with the same retry policy. Put the held-out result, not the development result, in the abstract and intro, and label the development analysis as exploratory.

### 4. The statistical analysis is underpowered and the bootstrap/p-value reporting is incoherent

**Problem.** The baseline FE is 2/183 = 0.011; V is 0. The paired difference is −0.011, which is the maximum possible reduction. There are only two discordant events. The 95% CI [−0.029, 0.000] has an upper bound exactly at zero because of the discrete point mass at zero. Table 4 reports p = 0.47 for Luna and p = 0.52 for MiniMax, but p is defined as “the bootstrap probability mass on the side that excludes zero,” which is not a standard p-value. For Luna, V − B2 cannot be positive, so the mass above zero is zero, not 0.47. The CI and the p-value are therefore inconsistent. The paper reports no power analysis and no minimum detectable effect.

**Why it matters.** The study cannot distinguish “no effect” from “the maximum possible effect.” The CI is compatible with a 2.9-point reduction, which is 2.6× the baseline rate. “The reduction is not statistically significant” is true but uninformative; the correct conclusion is that the study is underpowered and inconclusive. The “negative result” framing is an absence-of-evidence fallacy.

**Evidence.** Abstract (“The reduction is not statistically significant”); Section 7.1 (“−0.011 with 95% interval [−0.029, 0.000]”); Table 4 (p=0.47, 0.52); Appendix B (“2000 resamples,” “percentile interval”); Table 7 (B2 SUPPORT FP=2, gold non-support 183).

**Concrete fix.** Report the number of discordant pairs and use an exact McNemar or permutation test. Report a proper one-sided upper bound or a Bayesian posterior for the risk difference. Report power/MDE for the observed baseline rate and n=183 non-support claims. State explicitly that the data are compatible with both no effect and a meaningful reduction.

### 5. The 30-claim cross-model sweep cannot support the directional claims

**Problem.** Table 8 reports ΔFE = +0.000 [0.000, 0.000] for all four models. The text says “false endorsement never rises” and “the direction is stable,” but a degenerate [0, 0] interval is a null result, not evidence of no effect. The subset’s FE rate is up to 5% (Figure 4 caption), which is higher than the full-sample B2 rate of 1.1%, so the subset is not comparable. The claim that “Thirty claims can resolve a difference of roughly ten percentage points” is false: ten points on 30 claims is three claims, with a very wide interval. The four models share a training lineage (Section 7.4 admits this), the prompts were tuned on Luna’s development sample, and the subset is drawn from that same development sample, not from held-out data.

**Why it matters.** The cross-model claim is underpowered, confounded by prompt transfer and model lineage, and not an independent test. The paper uses a series of nulls to argue for a stable direction.

**Evidence.** Table 8; Section 7.4 (“all closed-weight,” “Thirty claims can resolve a difference of roughly ten percentage points,” “the closed-weight rows share a training lineage”); Figure 4 caption (“the largest false-endorsement rate in any row is 5%”); Section 6.1 (dev300 used for all prompt decisions).

**Concrete fix.** Run the sweep on the held-out split or a new sample. Report absolute FE rates and per-class counts, not only ΔFE. Pool the four models in a hierarchical model with a CI. Report the number of discordant pairs. Remove “stable” unless the pooled estimate is statistically distinguishable from zero.

### 6. The central mechanism is tautological and unvalidated

**Problem.** Section 4.3 says: “A disagreement … resolves to underdetermined.” Section 7.5 says V “abstains on every such claim by construction.” So “disagreement drives abstentions” is the algorithm, not an empirical finding. The more interesting quantity is the precision of the conflict signal: Table 9 shows B2 is correct on 60.0% of Luna development conflict claims and 64.2% of held-out conflict claims. The conflict signal therefore has only about 40% precision for B2 errors. Moreover, the D0 and D1 judgments come from different roles and policies — a claim-visible auditor versus a claim-blind reader plus a claim-visible judge — so “two readers of the same corpus” is a misdescription. The four-way labels and the conflict code are not scored or human-validated.

**Why it matters.** The paper’s main mechanistic claim — “scope disagreement, not retrieval, is the bottleneck” — is not identified. The conflict signal may be a weak uncertainty detector, and the asymmetry between the D0 and D1 roles may be producing the disagreement.

**Evidence.** Section 4.3; Section 7.5 (“V abstains on every such claim by construction”); Table 9 (B2 acc. 0.600 on differ, 0.642 held-out); Section 7.5/8/11 (“two readers of the same corpus”); Section 3.2 (four-way labels “reported but not scored”).

**Concrete fix.** Ablate the reconciliation rule: trust D0, trust D1, confidence-weighted, majority, and an LLM adjudicator. Report conflict precision/recall against B2 errors. Validate the four-way labels and the conflict code with human agreement on a sample. Call them “scoped judgments,” not “readers.”

### 7. The trade-off is not evaluated at matched coverage or with a cost model

**Problem.** V accepts only when the scopes agree: coverage 185/300 = 0.617, error 0.162. B2 accepts when the sealed reader cites at least one document, which is likely near full coverage. Figure 7 compares different acceptance rules and unspecified “high confidence” thresholds. The text still claims “the disagreement-based acceptance rule reaches low error at moderate coverage.” But B1 at full coverage has micro-F1 0.843 and FE 0.044; B2 has 0.747/0.011; V has 0.687/0.000. V is dominated by B1 and B2 on F1 and only wins on FE.

**Why it matters.** “Usable operating point” is unsupported without a cost ratio or a matched-coverage comparison. A reader-facing deployment would need to know the cost of a false endorsement relative to a missed support. The paper does not provide that.

**Evidence.** Section 7.7; Figure 7 caption (“The curves therefore compare acceptance policies, not calibrated probabilities”); Table 3 (B1 0.843/0.044, B2 0.747/0.011, V 0.687/0.000); Table 9 (agree 185, V error 0.162).

**Concrete fix.** Report risk–coverage curves under a common score or threshold for all methods. Compare at 50%, 70%, and 90% coverage. Report AURC. Specify an explicit cost model for false endorsement vs missed support, or remove the “usable operating point” claim.

### 8. Missing strong baselines and a compute-matched control

**Problem.** B2 is called “the strongest same-evidence configuration we could build without training” (Introduction), but B1 has higher micro-F1 (0.843 vs 0.747). No trained SciFact verifier is compared (e.g., VeriSci, CoVERT). RAFTS, RAV, SAFE, and CoV are cited but not implemented beyond prompt-level B2. There is no self-consistency or ensemble baseline at matched compute, no confidence-threshold selective baseline, and the citation auditor is never evaluated against SciFact rationale sentences.

**Why it matters.** Without a trained baseline and a compute-matched control, the paper cannot establish that V is a strong operating point or that the effect is due to staging rather than extra calls/tokens. The citation auditor — one of the four claimed roles — is a black box.

**Evidence.** Introduction (“strongest same-evidence configuration”); Table 3 (B1 0.843 vs B2 0.747); Section 7.7 (3 vs 2 calls, 6.4× tokens); Limitations (“No matched-budget control was run”); Section 4.1 (auditor described but no results).

**Concrete fix.** Add at least one trained SciFact baseline, a self-consistency/ensemble baseline at matched tokens, and a confidence-threshold selective baseline. Evaluate the citation auditor against the gold rationale sentences. Explain why B2, not B1, is the primary baseline.

### 9. Failure handling, cost accounting, and reproducibility are inconsistent

**Problem.** Section 4.2 says fail-closed rows are “excluded from scored metrics” and “never silently remapped into a scientific verdict.” But Table 5’s “all rows” accounting scores them as NEI. Section 5.4 says the held-out run “does not use the retry policy,” while the method description says “the runner retries it, up to four attempts per claim.” Table 12 takes V’s cost from the held-out run and B2’s from the development run. V is said to issue three calls per claim, but the pipeline has seven steps and “several roles may call the same underlying model.” Model versions, API dates, temperatures, and seeds are not reported; closed-weight models can change silently.

**Why it matters.** The reliability and cost claims are not comparable, and the held-out method is not the method described. The “all rows” sensitivity analysis contradicts the stated fail-closed principle.

**Evidence.** Section 4.2; Table 5 (“all rows … the conservative NEI”); Section 5.4; Table 12 (“for V is the held-out run: the development sidecar retains only the calls of its final resume pass”); Section 7.7 (“V issues three calls per claim”); Section 5.3 (closed-weight models, no snapshots).

**Concrete fix.** Introduce a separate “no prediction” category and coverage-aware metrics; do not map execution failures to NEI. Apply the same retry policy to the held-out run. Log per-claim tokens and latency. Report model snapshots, API dates, temperatures, seeds, and multiple runs. Include code/dependency hashes in the freeze record.

### 10. The false-endorsement outcome is fragile to label noise and is not disaggregated

**Problem.** There are only two B2 false endorsements on development and three on held-out. The evidence oracle O also has one false endorsement (FE 0.005) despite gold rationales, suggesting judge bias or label noise. The paper does not audit the false endorsements, does not report FE separately for gold REFUTE versus gold NEI, and does not report the promised second denominator FEpred. For B2 Luna, FEpred = 2/69 = 0.029; for MiniMax, 6/106 = 0.057. The “1 in 100” framing depends entirely on the gold non-support denominator.

**Why it matters.** A single label error could flip the result. Endorsing a REFUTE claim is more costly than endorsing an NEI claim, but the paper aggregates them. The missing FEpred result makes the headline less robust than it appears.

**Evidence.** Abstract (“about 1 in 100”); Table 7 (B2 SUPPORT FP=2, predicted support 69); Table 3 (O FE 0.005); Section 6.3 (“We report the second denominator … as well”); Appendix B (FEpred defined but not tabulated).

**Concrete fix.** Audit all false endorsements and near-misses. Report FE separately for gold REFUTE and gold NEI, and report both denominators in the main table. Report SciFact inter-annotator agreement or a label-noise model. Use a cost-weighted FE if the two error types differ in severity.

## Minor issues

- “Four isolated roles” (abstract) vs the seven-step pipeline in Table 1 (proposer, gatherer, reader, judge, auditor, reconciler, renderer).
- “Three query forms per round” and “two retrieval rounds” (Section 4.2) vs “three query forms are issued per claim” (Section 4.1) vs “three query templates” (Section 5.2).
- Table 10 mixes “passages” (k=8) and “documents” (2400); recall@k is over documents, not passages.
- Figure 3’s y-axis is dominated by B0 = 0.448, making the B1/B2/V differences hard to read.
- Table 8’s [0.000, 0.000] intervals are degenerate; state that they reflect zero discordant pairs, not precision.
- “Matches the baseline’s” (Section 7.5) vs held-out V 0.842 vs B2 0.871; MiniMax V 0.925 vs B2 0.911.
- “The comparison does not depend on the choice” (Section 7.1) is vacuous on development because there were zero failures; no all-rows paired CI is reported for held-out.
- “On all 300 scored claims” (Section 7.1) vs held-out 262; clarify in the abstract.
- “Two model families on the full samples” (Section 5.3) vs MiniMax has no held-out run and an incomplete matrix.
- “Open-weight rows of the sweep” (Section 10) vs “all closed-weight” (Section 7.4, Table 8).
- Appendix F’s `tools/opencode_bridge.py` is a de-anonymization risk.
- Several 2026 references (Hirsch, Li, Yang, Yu) lack venues/URLs; MARCH is cited twice (Li et al. 2026; Qwen-Applications 2026).
- “Nine refuted claims … four … five … none” (Section 7.4) is hard to reconcile with the per-model REFUTE TP counts (9, 8, 9, 9; V 5 each); provide the claim-level matrix.
- “The largest false-endorsement rate in any row is 5%” (Figure 4 caption) is higher than the full-sample B2 1.1%; do not use it to support “near zero.”
- “MiniMax is a markedly better verifier” (Section 7.3) is a cross-harness comparison; soften or remove.
- Calibration: raw numbers are promised (Sections 2.3, Appendix C) but only calibrated Table 11 is reported; Figure 6 bins with at least three claims are unstable.
- Figure 7’s “high confidence” thresholds are unspecified, especially for MiniMax, which has no calibration split.
- The case-study selection rule “deterministically” is unspecified; no random sample or coding protocol is given.
- The error taxonomy categories overlap: a SUPPORT prediction on gold REFUTE is both a false endorsement and a missed contradiction.

## Internal inconsistencies between abstract/intro/results/tables

| # | Claim | Conflicting evidence |
|---|-------|----------------------|
| 1 | Abstract: “finds only 43% of supported claims, compared with 57%.” | Held-out Table 5: V SUPPORT R 0.368 (scored) or 0.315 (all rows), B2 0.581. The abstract uses development numbers without saying so. |
| 2 | Abstract: “38 validator requests failing closed.” | Section 7.1 and Table 5: 38 claims, not necessarily 38 requests; V is scored on 262/300. |
| 3 | Abstract: “A separate 300-claim held-out sample.” | Table 5: V held-out n=262; the paired comparison is on 262, not 300. |
| 4 | Abstract: “The direction is stable … the cost appears as withheld contradictions.” | Table 7: SUPPORT R 0.573→0.427 and REFUTE R 0.790→0.597 (Luna); 0.855→0.692 and 0.903→0.823 (MiniMax). Section 7.4 admits: “the loss is not exclusive to REFUTE.” |
| 5 | Intro: “Our preregistered primary outcome … On the frozen development sample … −0.011 [−0.029, 0.000].” | Section 6.4: the comparison was “preregistered before the held-out run.” Section 6.1: development was “used for all development and prompt decisions.” |
| 6 | Section 4.2: fail-closed rows are “never silently remapped into a scientific verdict.” | Table 5 “all rows” scores fail-closed rows as NEI. |
| 7 | Section 7.2: “V’s zero false endorsement is thus a property of the reconciliation policy, not of the retrieval.” | Abstract and Introduction frame the result as testing whether “searching beyond the supplied citations reduces it.” |
| 8 | Table 4: Luna p=0.47 with CI [−0.029, 0.000]; MiniMax p=0.52 with CI [−0.046, 0.011]. | The p definition is incoherent; for Luna, V−B2 cannot be positive, so the “mass on the side that excludes zero” cannot be 0.47. |
| 9 | Table 8: ΔFE = 0.000 [0.000, 0.000] in all four models. | Figure 4 caption: “the largest false-endorsement rate in any row is 5%.” ΔFE=0 does not mean FE=0. |
| 10 | Section 7.5: “matches the baseline’s.” | Held-out: V 0.842 vs B2 0.871; MiniMax: V 0.925 vs B2 0.911. |
| 11 | Section 10: “the open-weight rows of the sweep.” | Section 7.4 and Table 8: “all closed-weight.” |
| 12 | Section 5.3: “two model families on the full samples.” | MiniMax has no held-out run and an incomplete matrix; Table 3 omits B0, B3, O for MiniMax. |
| 13 | Section 4.3: “A disagreement, or a failed D0 audit, resolves to underdetermined.” | Section 4.2: execution failures are excluded from scored metrics; a “failed D0 audit” is ambiguous between a citation-inadequacy judgment and a parse failure. |
| 14 | Section 7.7: “V issues three calls per claim.” | Table 1 has seven steps; Section 4 says “several roles may call the same underlying model”; the reconciler and renderer are not obviously counted. |

## Overclaims

- **“Independent evidence” / “searching beyond the supplied citations.”** D1 is BM25 over the same frozen corpus; unique annotated yield is 0.000. The paper does not test external or open-domain retrieval.
- **“Multi-agent.”** The system is a pipeline of prompts to the same model, not independent agents with debate, tools, or separate knowledge.
- **“Preregistered.”** No registration ID, date, or public analysis plan is given. The development sample was used for prompt decisions, and the held-out comparison is absent from Table 4. A hash freeze is a reproducibility mechanism, not a preregistration.
- **“Negative result.”** The study is underpowered; the CI includes a 2.9-point reduction, 2.6× the baseline. This is inconclusive, not evidence of no effect.
- **“The direction is stable.”** The evidence is a series of nulls, a degenerate [0,0] interval, shared model lineage, and a sweep on the development sample.
- **“The cost appears as withheld contradictions.”** On the full samples, SUPPORT recall also falls substantially; only the 30-claim subset shows a REFUTE concentration, and that subset is underpowered.
- **“The system can distinguish missing from unresolved evidence.”** The four-way labels are not scored or human-validated.
- **“The disagreement-based acceptance rule reaches low error at moderate coverage.”** The acceptance rules differ by method, thresholds are unspecified, and there is no matched-coverage comparison.
- **“The comparison does not depend on the fail-closed accounting.”** This is shown only for FE on development, where there were zero failures; the held-out paired CI under all rows is missing.
- **“Checkable statement” of one held-out run.** The freeze record does not enforce a single execution; it only checks configuration hashes.
- **“Strongest same-evidence baseline.”** B1 has higher micro-F1 than B2 (0.843 vs 0.747).
- **“Full factorial.”** V is not a cell in the 2×2; V-D1 is derived from V predictions, not run.
- **“Two readers of the same corpus.”** The D0 arm is a claim-visible auditor; the D1 arm is a claim-blind reader plus a claim-visible judge.
- **“All closed-weight.”** Section 10 refers to “open-weight rows of the sweep,” which do not exist in Table 8.
- **“False endorsement at or near zero.”** MiniMax V is 0.016 vs B2 0.033, and the 30-claim subset reaches 5%; “near zero” is doing rhetorical work.

## Missing related work or baselines

- **Trained SciFact verifiers:** Wadden et al. (2020) VeriSci, CoVERT, and SciFact-Open baselines. The paper uses only prompt-level conditions.
- **Atomic factuality and citation quality:** FActScore (Min et al., 2023), ALCE (Gao et al., 2023), Attributed QA (Bohnet et al., 2022), Rashkin et al. (2021) attribution, and citation-auditing work. These are directly relevant to the proposer, judge, and auditor.
- **LLM-as-judge bias and reliability:** Zheng et al. (2023, MT-Bench), Wang et al. (2023, “not fair evaluators”), Ye et al. (2024, “Justice or Prejudice?”), and self-preference bias. The paper uses the same model for all roles without discussing these biases.
- **Selective classification and abstention:** Chow (1970), Geifman and El-Yaniv (2017), conformal prediction (Angelopoulos and Bates, 2021), and risk–coverage analysis. The paper’s selective-use analysis lacks this framing and a proper confidence baseline.
- **Compute-matched ensembles:** self-consistency (Wang et al., 2022), multi-agent debate (Du et al., 2023; Irving et al., 2018), and verifier ensembles. These are the obvious controls for the 6.4× token confound.
- **Retrieval-augmented verifiers cited but not compared:** RAFTS (Yue et al., 2024), RAV (Zheng et al., 2024), SAFE (Wei et al., 2024), and CoV (Dhuliawala et al., 2024).
- **Calibration of LLMs:** Jiang et al. (2021), Kadavath et al. (2022), and the temperature-scaling literature beyond Guo et al. (2017).
- **Scientific claim verification:** SciClaims and Missci are cited as boundaries, but no comparison is made; CiteWorth and related scientific attribution work are missing.

## Questions for authors

1. What is the preregistration ID/date and the exact analysis plan? Was the development analysis preregistered? Why is the primary test on development rather than held-out?
2. Add the held-out row to Table 4. What is n paired: 262 or 300? Report the all-rows paired CI and the failure breakdown by stage, type, and gold label.
3. Why did the held-out run not use the retry policy? How many claims fail at the reader, judge, auditor, and reconciler? Are failures correlated with gold SUPPORT?
4. How many discordant pairs drive the FE estimate? Report McNemar/exact p and a proper CI. Explain p=0.47 with CI [−0.029, 0.000].
5. What is the power/MDE for FE at n=300 with 183 non-support claims? Why was no power analysis reported?
6. What exactly does B2’s compare step see versus V’s judge? Please give B2 the passages or restrict V’s judge to the sealed record, and rerun the comparison.
7. Why B2 rather than B1, given B1’s higher F1 (0.843 vs 0.747)? What makes B2 the “strongest” baseline?
8. How do you separate staging from the 6.4× token cost and the extra retrieval round? Please report a compute-matched control.
9. Why is V-D1 derived rather than run? Please run it independently.
10. How do you validate the four-way labels and the conflict code? Report human agreement and conflict precision/recall.
11. How do you know D1 found no new evidence when 92.6% of retrieved documents are unjudged? Please audit the unannotated documents and run a citation-perturbation experiment.
12. Why are the 30-claim sweep results described as “stable” when all ΔFE CIs are [0,0]? Report absolute FE rates and a pooled/hierarchical test.
13. Why does Section 10 mention “open-weight rows of the sweep”? Please correct the record.
14. Please report model snapshots/API dates, temperature, seeds, and at least three runs per condition.
15. Please report FE by gold REFUTE vs gold NEI, both denominators, and an audit of the 2/3 false endorsements.
16. Please report per-claim cost with per-claim logging for both families, not per-call cost from different runs.
17. Please report the raw versus calibrated numbers, as promised in Sections 2.3 and Appendix C.
18. Please specify the Figure 7 thresholds and compare methods at matched coverage.

## Score

**Score: 2/5 (reject). Confidence: 4/5.**

The paper is transparent, honest about its negative result, and has a credible artifact plan. But the central experiment does not test the stated hypothesis, the V–B2 comparison is confounded by evidence access and a 6.4× compute difference, the preregistered test is not the one reported, the statistics are underpowered and internally inconsistent, and several central claims conflict with the paper’s own tables. The strengths are real, but the contribution is not established at the level required for a top NLP venue.
