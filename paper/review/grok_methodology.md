# Methodology / statistics review (external, skeptical)

Reviewer stance: check the paper against **code and saved prediction files**, not the prose. Numbers below are computed from `artifacts/` (gitignored live runs) and the checked-in metric JSON under `docs/paper-assets/tables/`. No files other than this review were edited.

Verdict key: **CONFIRMED** (code + artifacts agree with the claim, or the flaw is real), **REFUTED** (paper/code disagree, or the claim is false), **UNCLEAR** (artifacts do not contain the field needed).

---

## Item-by-item verification

### 1. `d0_d1_conflict` definition; NEI-vs-NEI

**CONFIRMED** (definition + count). A D0=`unaddressed` vs D1=`underdetermined` pair **is** a conflict.

Conflict is **four-way string inequality**, not a 3-way scientific disagreement. `reconciled_judgment` copies `d0_d1_conflict` whenever the two completed labels differ, or either arm failed (`src/validator/fixture_pipeline.py:397–408`). `reconcile()` does the same (`src/validator/reconcile.py:84–100`). Unaddressed and underdetermined both map to NEI (`src/validator/validator_v/labels.py:27–31`), so two NEI flavours still conflict.

Mechanism tables count the rationale code, not scored-label disagreement (`scripts/paper/make_tables.py:1157–1162`).

From `artifacts/api/dev300/v/predictions.jsonl` (300 ok rows):

| | n |
|---|---|
| `d0_d1_conflict` | **115** (matches `\lunadevConflictN`) |
| of which both map to NEI | **60 / 115 (52%)** |
| `underdetermined` vs `unaddressed` | 55 |
| `unaddressed` vs `underdetermined` | 5 |
| remaining 55 | at least one of SUPPORT/REFUTE |

The “disagreement detector” story is inflated by one-NEI-flavour-vs-the-other. On the scored 3-way space those 60 are **agreeing NEI**.

**Fix:** Redefine conflict on the scored 3-way labels (or report a 2×2 of {support, contradict, NEI_unaddressed, NEI_underdetermined}). Recompute Table 9 excluding the 60 NEI-vs-NEI rows; state that 52% of “conflicts” are unaddressed/underdetermined swaps.

---

### 2. B2 compare inputs vs V judge; 3-way vs 4-way; confounded factorial

**CONFIRMED** — the 2×2 is confounded by prompt, label space, and inputs beyond the two named factors.

| Cell | Decision step sees passages? | Label space | Prompt |
|---|---|---|---|
| B2 compare | **No.** Claim + sealed `{answer, cited_doc_ids}` only (`src/validator/same_evidence/b2.py:65–66, 296–323`; `prompts/same_evidence/b2_compare_v1.txt`) | SUPPORT/REFUTE/NEI | compare prompt |
| V D1 judge | **Yes.** Claim + sealed record + **passage text** (`src/validator/live_judgment.py:444–465`; `prompts/judgment/judge_live_v1.txt`) | 4-way, then mapped | judge prompt |
| B1 / B3 | Yes (evidence dumped as text) (`src/validator/baselines/evidence.py:46–59`; `prompts/baselines/claim_visible_judge_v1.txt`) | 3-way + verbalised confidence | claim-visible judge |

Appendix contracts already admit this (`paper/main.tex:1259–1261` vs `1249–1252`). Named factors are only “evidence access (D0 vs D1)” and “reading policy (claim-visible vs evidence-first)” (`paper/main.tex:567–571`). Extra factors: (i) compare-without-passages vs judge-with-passages, (ii) 3-way vs 4-way, (iii) different prompts, (iv) V-D1 not independently run (item 3), (v) V adds auditor + reconciler.

B1 beating B2 on micro-F1 is therefore **not** a clean test of “evidence-first vs claim-visible”: B2’s compare step is information-starved relative to B1.

**Fix:** Either re-run a B2′ whose compare step also sees D0 passages (matched to the V judge contract), or drop the factorial causal language and call Table 2 a prompt-system comparison.

---

### 3. V-D1 mapping; is it a fair arm?

**CONFIRMED** as a mapping; **REFUTED** as a fair factorial cell.

`extract_vd1.py:16–34` copies `d1_label_4way` → native via `map_four_way_label` and **inherits V’s `execution_status`**. Fail-closed V rows stay fail-closed even if D1 completed. On held-out, 38 V-D1 fail-closed are exactly V’s 38 (`gpt-6-luna_heldout300_V-D1_metrics.json`: `n_skipped_not_ok=38`). One held-out failure has `d1_label_4way=contradicted` (D1 finished) but is still dropped.

V-D1 is also a 4-way judge-with-passages, not a B2-style compare-without-passages (item 2). It is a **diagnostic slice of V**, not the D1 analogue of B2.

**Fix:** Label V-D1 “derived D1 slice of V, not a matched arm.” To test evidence access, re-run an independent D1 evidence-first pipeline with B2’s compare contract.

---

### 4. Retry policy vs seeing results; why B2/B1/B3 numbers moved

**CONFIRMED** — retries and baseline re-runs happened **after** the first primary numbers were known. Family clustering did **not** change; B2 **was** re-run.

Timeline (artifact mtimes + `git log`):

| When | What |
|---|---|
| 2026-09-25 02:15–03:27 UTC | First Luna dev B2 + V. V: 32 fail-closed. Sidecars: `artifacts/same_evidence_b2_dev300/`, `artifacts/validator_v_dev300/` |
| 2026-09-25 03:48–05:01 UTC | Held-out B2 then V (38 fail-closed). **No retry.** |
| 2026-09-26 07:08 IST | `paper/RESULTS.md` committed with those numbers (V fail-closed 32, B2 SUPPORT recall **0.530**, **226** families, T=**1.8**). `docs/freeze.json` first committed in the same window (`d5dac68`) |
| 2026-10-20 | `scripts/paper/drop_failed_rows.py` and `scripts/run_api_dev300.sh` added (`7a4876c`). Full Luna matrix re-run into `artifacts/api/dev300/` |

Oct 20 vs Sep 25 prediction files:

- **B2 was re-run**, not merely re-scored: 26/300 labels flipped (`NEI→SUPPORT` 11, `NEI→REFUTE` 7, `SUPPORT→NEI` 6, `REFUTE→NEI` 2). SUPPORT recall 62/117=0.530 → 67/117=0.573. Micro-F1 stayed 0.747 by coincidence. Config hash unchanged (`9fcfc49aeff0`), so freeze still “matches.”
- **V is not a clean retry of the 32 failures:** 32 previously-failed rows were recovered, **but 14/268 previously-ok labels also flipped.** New V `run_id` uses config hash `0c4a3fb21c2e`, **not** the frozen `c3d7773f7287`. Paper DEV V is a post-freeze configuration.
- **B1/B3/B0/O** all have Oct 20 timestamps; 2×2 cells in `RESULTS.md` vs `macros.tex` all moved (e.g. B3 micro-F1 0.790→0.800, B1 FE 0.049→0.044).
- **226 → 246 families:** not a clustering change (`src/evaluation/families.py` last touched 2026-09-26). Old pairing used 268 claims (32 V dropped) → 226 families; new pairing uses 300 → 246. Twenty newly included claims added twenty families.

Temperature 0 is not actually sent to official OpenAI (`src/validator/same_evidence/b2.py:504–517`: “Official OpenAI omits temperature (model default only)”). Re-runs at “T=0” are model-default samples. That explains 26 B2 flips.

**Fix:** Report Sep 25 and Oct 20 as two development snapshots, or freeze the Sep 25 files as the preregistered DEV analysis. Do not silently replace B2. State that cloud requests omit `temperature`. Call the Oct 20 matrix exploratory.

---

### 5. Public timestamped preregistration?

**REFUTED** as public preregistration. **CONFIRMED** as an internal hash lock written from already-completed **development** runs, then used for held-out.

- No OSF / AsPredicted / registry URL in the repo (`docs/freeze.json`, `docs/RESEARCH_PLAN.md`, `paper/main.tex`).
- `docs/freeze.json` is an internal hash gate (`src/validator/split_policy.py:68–80`). `scripts/write_freeze.py:11–18, 61–70` copies hashes from **dev** sidecars (`artifacts/same_evidence_b2_dev300`, `artifacts/validator_v_dev300`) and records `code_commit: 57429ca` (2026-09-22).
- Held-out ran 2026-09-25 03:48–05:01 UTC, **after** those dev results (including the null and 32 fail-closed) existed. Freeze file committed 2026-09-26 (`d5dac68`). So: locked before held-out, **not** locked before seeing the primary DEV outcome.
- `freeze.json` `"sample"` points at **dev300**, not the held-out manifest (`scripts/write_freeze.py:66`).
- Paper DEV V (`0c4a3fb21c2e`) is **not** the frozen V hash (`c3d7773f7287`).

**Fix:** Say “internally hash-locked before the local held-out run; development outcome was already known.” Do not say “preregistered.” If a public registration is added, it cannot cover the Oct 20 re-runs.

---

### 6. Held-out 38 fail-closed: timeout / parse / transport?

**UNCLEAR** at the parse-vs-transport-vs-timeout grain. **CONFIRMED** at stage grain.

Saved rows (`artifacts/held_out/v/predictions.jsonl`) have `execution_status` ∈ {ok, failed} only: **38 `failed`, 0 `timeout`**. The reconciler **overwrites** the parse/transport reason with `d0_d1_conflict` and maps any incomplete arm to `failed`, not `timeout` (`fixture_pipeline.py:402–407`; `_failed_judgment` originally stores `live_parse_failed` / `live_timeout` / `live_endpoint_unavailable` at `live_judgment.py:194–205, 489–519`, then those codes are discarded).

Inferrable from placeholders (D1 failure label is schema `unaddressed`, `live_judgment.py:489–499`):

| Pattern | n | Reading |
|---|---|---|
| D1=`unaddressed`, no `d0_not_repaired_from_d1` | 35 | D1 reader/judge failed; D0 completed |
| `d0_not_repaired_from_d1` and D1=`unaddressed` | 2 | both arms failed |
| `d0_not_repaired_from_d1` and D1=`contradicted` | 1 | D0 audit failed; D1 completed |
| `execution_status=timeout` | 0 | timeouts collapsed to `failed` |

**Fix:** Persist the pre-reconcile reason (`live_parse_failed` / `live_timeout` / `live_endpoint_unavailable`) on the prediction row. Add a held-out failure table. Do not imply a timeout count you cannot recover.

---

### 7. McNemar, degenerate bootstrap, odd `p`, power

**CONFIRMED** on all four sub-claims.

**Exact McNemar** (gold non-support, both execution-ok, FE = predicted SUPPORT):

| Split | n paired non-support | B2-only FE | V-only FE | two-sided exact p |
|---|---|---|---|---|
| Dev Oct 20 | 183 | 2 (`scifact:175`, `scifact:1307`) | 0 | **0.50** |
| Dev Sep 25 (268 V ok) | 161 | 2 (`scifact:175`, `scifact:658`) | 0 | **0.50** |
| Held-out | 156 | 2 (`scifact:879`, `scifact:956`) | 0 | **0.50** |

Held-out B2 has a third FE (`scifact:907`) dropped from the pair because V fail-closed. Need ≥6 one-sided discordant pairs for exact two-sided McNemar at α=0.05; observed N=2 can never reject.

**Bootstrap is degenerate when V FE ≡ 0.** Every resample has V FE\* = 0, so Δ\* = −B2_FE\* ≤ 0. The percentile interval is pinned at 0 on the right (`[-0.029, 0.000]` / `[-0.033, 0.000]`). `_excludes_zero` requires `ci_high < 0` (`bootstrap.py:353–355`), so a bound of exactly 0 never “excludes zero.” This is a property of a point-mass contrast, not evidence of a small effect.

**`p` column is not what the caption says, and is not a valid test of Δ=0.**

- Caption (`paper/main.tex:658–660`): “bootstrap probability mass on the side that excludes zero; a value near 0.5 means the interval straddles zero.”
- Code (`src/evaluation/holm.py:63–75`; written at `scripts/paper/make_tables.py:257`): `(1 + #{|draw| ≥ |θ̂|}) / (B+1)`. Draws are centred at θ̂, not at 0, so this p-value → 1 for a large precise effect and sits near 0.5 whenever |θ̂| is typical of |draws|. Reported 0.47 / 0.44 match `p_raw` in the JSON, not the caption.

**Power.** B2 FE = 2/183 ≈ 1.09%. If V is truly zero, discordant count ~ Binomial(183, 0.011). P(X ≥ 6) ≈ **0.016**. Detecting a one-point drop with 80% power needs E[events] ≈ 8 ⇒ n_nonsup ≈ 730, not 183. No power calculation exists in the repo (search over `*.py`/`*.md`/`*.tex` other than the sweep sentence). The claim “the full sample was sized for the one-point false-endorsement rate” (`paper/main.tex:813–814`) is an assertion about **describing** a 1% rate (SE ≈ 0.8 pp), not about detecting a 1 pp **difference**.

**Fix:** Report McNemar (b=2,c=0,p=0.50) as the primary test; drop or replace the `p` column with a defined quantity; state that the study is not powered for FE; delete “sized for.”

---

### 8. Holm adjustment reported?

**REFUTED** as a reported result. **CONFIRMED** as dead code.

Holm runs only on the non-primary metric in `_METRICS`, i.e. a **family of one** (`false_endorsement_pred_sup`) (`bootstrap.py:181–183`). `p_holm = p_raw` (no-op). Stored in `gpt-6-luna_dev300_b2_vs_v.json:5759–5770` etc. **Never printed** in `t1b_*.tex` or the body. Comment says “later F1 / recall” are adjusted together; they are not passed in.

**Fix:** Delete the Holm sentence, or actually adjust a declared secondary family (micro-F1, SUPPORT recall, FE_pred) and print `p_holm`.

---

### 9. Held-out V-D1 FE 0.032 vs B2 0.017

**CONFIRMED.** Paper never discusses it.

`gpt-6-luna_heldout300_V-D1_metrics.json:163–168`: FE = 5/156 = **0.03205**. B2 held-out: 3/176 = **0.017** (`t1_heldout300.tex:8–9`; `\lunaheldVDOnefe`, `\lunaheldBTwofe`). On the 156 paired non-support claims, V-D1 has 5 FEs vs B2’s 2 (B2’s third FE is in a V fail-closed row). Independent retrieval **increases** false endorsement relative to reading D0, before reconciliation zeros it by abstaining.

Events: V-D1 `{183, 507, 879, 956, 1226}`; B2 `{879, 907, 956}`.

**Fix:** One paragraph in Results/Discussion: D1-only is the **less** conservative arm on held-out; V’s zero FE is the reconciler, not retrieval. This is the most important unused number in the paper.

---

### 10. Cost table mixes splits; “six times”; B2@k

**CONFIRMED** mix and approximate “six times.” **CONFIRMED** B2@k exists and was not run. Cheap with a caveat.

`measured_costs` picks, per condition, the sidecar with the most calls (`scripts/paper/make_tables.py:708–748, MIN_CALLS_FOR_COST=100`). Oct 20 V sidecar has **3 calls** (last resume only), so V tokens come from **held-out** (858 calls, 2,229,331 tokens). B2 tokens come from **Oct 20 dev** (600 calls, 362,895 tokens). Caption admits this (`paper/main.tex:1034–1036`; `t3_cost.tex` column “measured on”).

Design ratio: 3 × 2,598 / (2 × 605) = **6.44**. Old `RESULTS.md` used per-claim totals 7,462 / 1,209 = **6.17**, k=7. “Six times” is fair as order of magnitude if you accept mixed splits and per-call averaging.

B2@k: `src/validator/baselines/majority.py` + tests in `tests/test_baselines.py:77–80`. No live runner invocation. `docs/RESEARCH_PLAN.md:136–148` and Limitations say it was skipped. It could be run by repeating B2’s **compare** step k times and majority-voting (conservative tie-break NEI > REFUTE > SUPPORT). **Caveat:** official OpenAI omits `temperature` (item 4), so k i.i.d. samples at T>0 need a client change. Not free, but far cheaper than V (one extra call per seed per claim, not three full stages).

**Fix:** Put B2 and V cost on the same split, or report both. Either run B2@k on a 50-claim probe or strike “matched inference budget” from RQ1 (`paper/main.tex:294–296`).

---

### 11. Unique yield 0; is RQ1 untestable? Corruption experiment?

**CONFIRMED** unique yield 0 is structural. **CONFIRMED** RQ1’s motivating mechanism (independent retrieval repairs a **wrong citation**) cannot occur on this gold. Codebase can support a corruption experiment with a thin adapter; nothing implements it.

`scripts/paper/make_retrieval_metrics.py:20–21, 106–118` defines “annotated” as cited docs that carry SUPPORT/CONTRADICT rationales. On SciFact that set is a **subset of `cited_doc_ids`** by construction. Direct check: 179/179 annotated claims on dev300, 188/188 held-out, 59/59 calibration have annotated ⊆ cited. `n_annotated_retrieved_not_cited = 0` (`retrieval_metrics.json:20`; `t5_retrieval.tex:11,15`). Retrieval can only add **unjudged** context (unjudged rate 0.93).

A “wrong citation” in the gold sense is a cited doc without a rationale — there is no gold document outside D0 to recover. RQ1 as written (matched budget, independent retrieval **plus** staging vs same-evidence) is only testing staging/reconciliation, not evidence acquisition.

**Feasible experiment:** citation corruption / swap of D0. Shuffle or replace `cited_doc_ids` with random corpus abstracts, keep gold labels, run B2 (D0-only) vs V-D1 (fresh BM25). Hypothesis: B2 FE/recall collapse toward NEI; V-D1 recall of SUPPORT/REFUTE is preserved if retrieval works. Implementation path already exists: `src/validator/validator_v/cited_d0.py:38–54` and `src/validator/same_evidence/inputs.py:209–271` both build D0 from native `cited_doc_ids`. A preprocessor that writes a corrupted claims JSONL (or a `--corrupt-d0` flag) feeds both runners without touching prompts. Do **not** use gold rationales as the swap set.

**Fix:** Reframe RQ1 as “does conservative reconciliation reduce FE given that D0 already contains the gold docs?” Run the corruption experiment before claiming anything about independent retrieval.

---

### 12. Calibration T=0.4 fitted on 100, reported in-sample

**CONFIRMED.**

`scripts/paper/make_calibration.py:159–167, 194–210` fits T on the calibration split, then writes **both** the calibration split and dev300 into `t4_calibration.tex`. First row: n=100, Brier 0.307, NLL 0.586, ECE 0.021, T=0.4 — **in-sample**. Second row is the honest transfer (dev300). `fitted_on: "calibration"` in `calibration_by_family.json`.

Older `paper/RESULTS.md:43` fitted T=1.8 on **n=300** (the evaluation sample). That leak was replaced by a smaller in-sample report, not removed.

Reliability figure prefers `dev300` (`make_figures.py:693`), which is fine; the table is not.

**Fix:** Drop the calibration-split metrics row, or mark it “fit set, not a result.” Calibration is only for B1, not V/B2 — say so in the table title, not only the caption.

---

### 13. Other methodological flaws

**CONFIRMED**, several.

1. **SciFact in pretraining / parametric leakage.** B0 (claim only, no evidence) micro-F1 0.547, SUPPORT recall 0.863, FE 0.448 (`macros.tex:2–7`). The model already “knows” these claims. Dev300 is a seed-42 draw from the **train** pool (`scripts/make_dev300_sample.py:27–28, 56–62`; `sample_from_manifest` is `random.sample`, not family-blocked — `claim_sample.py:122–131, 158–172`). Held-out is SciFact public dev, public since 2020. Undiscussed.

2. **Family grouping of samples is overclaimed.** Paper: “Both samples group claims by cited-document family so that paraphrases do not straddle the comparison” (`paper/main.tex:556–557`). Sampling is unstratified `rng.sample`. Bootstrap clusters by cited-doc connected components (`families.py:1–7, 19–63`). **36 families straddle calibration and the 709-claim train pool vs the 300-draw**; 48 cited documents are shared between calibration and dev300; **95 cited documents** are shared between held-out and dev300. Paraphrases can and do straddle.

3. **Retry + omitted temperature ⇒ non-replicable point estimates.** Item 4. Official OpenAI drops `temperature`. “All models run with temperature 0” (`paper/main.tex:487`) is false for the Luna family.

4. **Fail-closed sensitivity on DEV is vacuous.** After retries, scored-only and all-rows are identical (`t1c_sensitivity.tex:8–11`). The check only bites on held-out.

5. **Primary metric is almost a two-event statistic.** FE is 2/183 (dev) and 3/176 (held-out). One flipped label moves the headline.

6. **RQ1 “matched inference budget” is false.** V is ~6× B2 tokens; B2@k not run (item 10).

7. **Proposer, second retrieval round, renderer** are specified (`paper/main.tex:358–391, 399–409`) and never scored. Evaluation is SciFact-native claims with one BM25 round.

8. `paper/RESULTS.md` is stale relative to `macros.tex` (32 fail-closed, recall 0.530, 226 families, T=1.8). Readers who open the repo will cite the wrong numbers.

---

## Prioritized findings

### Critical

1. **Primary test has no power and a degenerate interval.** Exact McNemar on 2 vs 0 discordant FE pairs is p=0.50 on both splits. Percentile bootstrap with V FE≡0 is pinned at 0. The `p` column is an invalid bootstrap p, mis-captioned. There is no power analysis; “sized for the one-point rate” is unsupported. *Fix:* report McNemar; drop `p`; state the study cannot detect a 1 pp FE drop (need ~730 non-support claims, not 183).

2. **RQ1’s retrieval mechanism is untestable on SciFact.** Unique yield is structurally 0 (annotated ⊆ cited, 179/179). Independent retrieval cannot repair a wrong citation because there is no gold document outside D0. Held-out V-D1 FE **0.032 > B2 0.017** (5 vs 3 events; 5 vs 2 on the paired subset) — the independent arm endorses **more** falsely — and the paper never says so. V’s zero FE is the reconciler mapping any 4-way mismatch (including 60 NEI-vs-NEI) to underdetermined. *Fix:* reframe as a reconciliation paper; run a D0 citation-corruption experiment (`cited_d0.py` / `same_evidence/inputs.py` already consume `cited_doc_ids`).

3. **“Preregistered” is an internal lock written after the DEV null was seen; the paper’s DEV numbers are a later re-run.** Freeze hashes come from Sep 25 dev sidecars; held-out followed that afternoon; retries + full baseline re-run on Oct 20 changed B2 (26 labels), V (32 recovered **and** 14 previously-ok flips), B1/B3/O, family count 226→246, T 1.8→0.4. Paper DEV V config hash ≠ freeze. No public registry. *Fix:* call it hash-locked-before-held-out; publish Sep 25 as the confirmatory DEV table or mark Oct 20 exploratory.

### Major

4. **2×2 factorial is confounded.** B2 compare does not see passages and is 3-way; V judge sees passages and is 4-way; V-D1 is a mapping that inherits V failures. Not a test of “evidence access × reading policy.” *Fix:* matched re-run or weaker language.

5. **Conflict definition inflates the mechanism.** 60/115 dev “conflicts” are unaddressed vs underdetermined (both NEI). *Fix:* conflict on 3-way labels; report the 60 separately.

6. **Held-out 38 fail-closed cannot be classified as timeout/parse/transport** because the reconciler drops the reason and maps timeout→failed. ~35 look like D1 placeholder `unaddressed`. *Fix:* persist the pre-reconcile reason.

7. **Holm is claimed and not reported** (family of one, identity adjustment, JSON only). *Fix:* delete or use.

8. **Cost “six times” mixes held-out V with dev B2; RQ1 promised a matched budget; B2@k is implemented and unused.** OpenAI client must send `temperature` before k-sample self-consistency is even defined. *Fix:* same-split cost; run or withdraw matched-budget language.

9. **SciFact contamination / train-pool sampling / family straddle** undiscussed (B0 recall 0.86; 95 shared cited docs held-out↔dev300; 36 families straddle calibration vs train draw). *Fix:* limitations paragraph; family-blocked sampling in any sequel.

### Minor

10. Calibration table includes the **fit split** (n=100, T=0.4 in-sample). Drop or mark it.
11. “Temperature 0” is omitted on `api.openai.com` (`b2.py:504–517`).
12. DEV fail-closed sensitivity is tautological after retries.
13. Stale `paper/RESULTS.md` vs generated macros.
14. Proposer / round-2 retrieval / renderer described, not evaluated.
15. FE is a two-event statistic; do not headline “V makes no such endorsement” without the McNemar and the V-D1 held-out reversal.

---

## Suggested paper-text patches (minimal)

- Abstract / RQ1: replace “preregistered” with “hash-locked before the local held-out run.” Add that V-D1 held-out FE exceeded B2, so zero FE is reconciliation, not retrieval.
- §Statistics: replace the `p` caption with McNemar (2 vs 0, p=0.50); delete Holm; delete “sized for.”
- §Factorial: “These cells also differ in label space and in whether the decision step sees passages; V-D1 is derived.”
- §Mechanism: “60 of 115 recorded conflicts are unaddressed vs underdetermined (both NEI).”
- Limitations: SciFact gold ⊂ citations; no public preregistration; Oct 20 retry re-run; OpenAI drops temperature; no B2@k; no power.
- Table 4: drop the calibration-split row.
- Table 3: one split, or an explicit asterisk on mixed sources.
