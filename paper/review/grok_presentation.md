# Presentation, consistency, and figure review

External review of `paper/main.pdf` (25 A4 pages, compiled 2026-10-25), `paper/main.tex`, `paper/tables/macros.tex`, `paper/tables/*.tex`, and every figure PDF. Each PDF page was rendered at 80 dpi and every figure at 120 dpi and inspected as images. No source files were edited.

**Verdict.** The paper is a draft of a negative result that the tables mostly support, wrapped in a title, abstract, and “three findings” that the full-sample numbers contradict. Layout is unfinished (empty author block, floats drifting 3–4 pages, two broken diagrams, one empty reliability plot). At ~9,250 words before the appendix and 20 pages of main matter, it is about 2× a typical ACL/EMNLP 8-page limit.

References below use compiled **PDF page**, **section**, `main.tex` line, and generated macros.

---

## 1. Visual inspection (pages and figures)

### Page 1 — title, empty author block, abstract

- **Title:** “Multi-Agent Validator System / Independent Evidence for Scientific Claim Verification”. The first line overclaims the architecture (see C4). The subtitle is ambiguous: “independent evidence” can mean the finding or the method.
- **Author / date / PDF metadata:** `\author{}` and `\date{}` are empty (`main.tex` 48–49). `pdfinfo` reports `Author:` blank. The compiled page has a large white gap between the title and “Abstract”. Looks like an unsubmitted draft.
- **Abstract** is one dense paragraph (~254 words; typical ACL limit is 200). It already contradicts itself: it correctly says V finds 43% of supported claims vs 57% for B2, then says “the cost appears as withheld contradictions” (see C1).
- **Artifact paragraph** between abstract and §1 is unusual for ACL and burns a third of page 1.

### Pages 2–4 — intro / related work / problem

- Readable, but §1 already spends a paragraph on limitations that §9 and §10 repeat.
- Figure 1 and Figure 2 are cited at the end of page 4; they land on pages 5–6.

### Page 5 — Figure 1 (architecture) + Table 1

**Figure 1 is structurally wrong and does not match its caption.**

- Caption (`main.tex` 319–324): solid arrows carry evidence; a dashed arrow is the only path by which the claim reaches the judge; D0 and D1 are judged separately; the reconciler never repairs one with the other.
- What the PDF shows: two disconnected rows. Top: Frozen corpus → Independent gatherer → Sealed reader → Judge. Bottom: Citation auditor → Reconciler → Claim card. The citation auditor has **no incoming D0**. There is no parallel D0/D1 structure. The “dashed claim path” is an orange elbow that is easy to miss. The proposer (Table 1, step 1) is absent. Fail-closed is a footnote, not a path.
- **Table 1** is fine and more informative than the figure. If space is tight, keep the table and drop or redraw Figure 1.

### Page 6 — Figure 2 (data flow)

**Figure 2 is incomplete and disagrees with its caption.**

- Caption: top lane = neutral question through retrieval and claim-blind reading; lower lane = original claim and citations to the scoped judges.
- What the PDF shows: the “D1 claim judge” box sits on the citation lane and has **no incoming arrow**. The “claim revealed after sealing” callout points at the reconciled card, not at the judge. The D0 auditor → reconciler edge bypasses the D1 judge. Several boxes look empty.
- Figures 1 and 2 tell the same story badly. Merge into one correct diagram (parallel D0 / D1 judges → reconciler; claim enters only after the seal; fail-closed as a side exit).

### Pages 7–9 — implementation, setup, condition matrix

- Dense systems prose (hashes, sidecars, retry). Table 2 (conditions) is clear and should stay in the main paper.
- RQ1 on page 4 (`main.tex` 294–296) asks about a **matched inference budget**. No such control exists (see C5).

### Page 10 — Tables 3 and 4

- Tables are readable and match `macros.tex`.
- Table 3 caption encodes the method legend; it is long but not overflowing.
- **Held-out main table is missing.** `paper/tables/t1_heldout300.tex` and `t1b_heldout300_paired.tex` are generated and never `\input`. Held-out results live only in prose and in the sensitivity table.

### Page 11 — Figure 3 (false endorsement) + Table 5

**Figure 3 does not match Table 3.**

- Table 3 / macros: Luna V-D1 FE = 0.016, MiniMax V-D1 FE = 0.033. Both conditions were run.
- Figure 3 prints `n/a` for V-D1 on both models. The caption says “Missing conditions were not completed.” That is false for V-D1.
- B0 (0.448) dominates the y-axis, so B2 (0.011) and V (0.000 / 0.016) are almost invisible — the primary comparison is the one you cannot see.
- **Rewrite the figure or drop it.** If kept: start the axis at 0–0.10, show V-D1, and pair each bar with SUPPORT recall. Table 3 already has the numbers; Figure 3 currently adds clutter.

### Page 12 — Tables 6 and 7

- Table 6 (ablation) **duplicates** Table 3’s micro-F1 and FE with extra “Evidence / Reading policy” columns. Merge (see §4).
- Table 7 is the most important table in the paper and is visually fine. It is also the table the abstract and intro bullet 3 contradict (C1).
- Table 6 MiniMax omits B0/B3/O — correctly, and the prose says so.

### Page 13 — Table 8 (sweep) floats *before* §7.4

- Table 8 appears at the top of the page; leftover §7.3 text and then §7.4 (“The shift across four models”) follow. Readers hit the 30-claim table before they are told it is a 30-claim table.
- All four rows are `closed` GPT-line models; GPT-6 Luna is the main model. The figure/table do not mark that one row is not a replication (C2).

### Page 14 — Figures 4 and 5

**Figure 4 (model sweep).** Readable dumbbells. The FE panel is four dots at 0% and carries no information. SUPPORT is almost flat (Astra 0.700→0.600 is one claim). REFUTE 0.8–0.9 → 0.5 is the only signal. Caption (`main.tex` 855–858) generalizes that signal as “SUPPORT recall and false endorsement barely move” — true on *this* subset, false on the full sample.

**Figure 5 (label distribution).** Clean stacked bars; numbers match macros (Luna 50/39/69/142; MiniMax 84/54/59/103). It appears *above* the §7.5 paragraph that introduces it. Held-out four-way counts (39/31/51/179) are never plotted.

### Page 15 — Table 9 (mechanism)

- Readable. Order in the surrounding prose flips (C6).
- When scopes **differ**, B2 is still right on 0.600 / 0.642 / 0.767 of claims while V abstains on all of them. That is the coverage cost; the caption buries it as “how often NEI happens to be the gold label.”

### Page 16 — Tables 10 and 11

- Table 10 (retrieval) is the constraint on every retrieval claim: unique yield **0.000**, unjudged rate **0.926**, annotated-not-cited **0**. Slight rounding drift vs macros (`0.849` in table vs `\retrievalRecall{0.85}`; `0.096` vs `0.10`; `0.926` vs `93`).
- Table 11 (B1 calibration) is a non-primary condition. Fine in an appendix; not worth a main-paper table *and* Figure 6.

### Page 17 — Figure 6 (reliability) + Discussion start

**Figure 6 is illegible as science and almost empty as a plot.**

- Two points, both near predicted probability 0.8–0.85. Most of the unit square is blank.
- Caption correctly says this is not a calibration result for V. Then why is it in the main paper, on the Discussion page, two pages after its citation (p. 15)?
- **Drop it.** Keep Table 11 in Appendix C if at all.

### Page 18 — Figure 7 (risk–coverage) + Table 12 (cost) + leftover Limitations

- **Figure 7:** seven curves, reused colors (two blues, two reds). The spike at coverage 0 is an artifact. Caption admits the acceptance rules differ (V: D0/D1 agree; B2: reader cited a document; B1/B3: verbalised confidence), so the figure does **not** compare methods on one axis. “Low error at moderate coverage” (`main.tex` 979–980) is not visually distinctive for V; B1 is lower.
- **Table 12:** V tokens come from the **held-out** run (2,598 tokens/call, 12.5 s median); B2 tokens come from **dev** (605, 2.6 s). Caption admits the mix. Per-claim cost is 3×2,598 vs 2×605 ≈ **6.4×**, which the prose calls “roughly six times” — acceptable, but the next figure hides the call multiplier.

### Page 19 — Figure 8 (accuracy vs cost) + Table 13 (failures)

- **Figure 8:** log-x scatter of micro-F1 vs *per-call* prompt tokens. V sits bottom-right among evidence-using methods (worse F1, more tokens). That supports the negative result, but the x-axis understates V’s cost by ignoring 3 vs 2 calls. B3 is even more expensive per call (3,064) with higher F1 than V — undiscussed.
- **Table 13** is wide but fits. It duplicates Figure 9 and Table 7’s FN counts. Keep one.

### Page 20 — Figure 9 (failure breakdown) + Ethics + Conclusion

**Figure 9 is the paper’s best figure and it refutes the abstract.**

- Luna V: tall blue stack = missed support (67); orange missed contradiction (25); red FE = 0.
- MiniMax V: missed support 36 vs missed contradiction 9.
- The figure lands on the **Ethics** page, four pages after its citation (p. 16). Move it next to Table 7 and write the abstract from it.

### Pages 21–25 — appendix and references

- Appendix A–C are useful and short.
- Appendix D (deferred human study) is a full protocol for a study that was not run. ACL reviewers will call it padding; keep 4–6 lines or drop.
- Table 14 (cases) is cramped; claim text wraps into the labels. Readable enough for an appendix.
- References: long URLs wrap; `Safe` should be **SAFE** (`main.tex` 197); several 2026 `@misc` items will draw “are these published?” questions.

### Layout / float scorecard

| Object | First cited | Appears | Problem |
|---|---|---|---|
| Fig 1 architecture | p. 4 | p. 5 | Broken diagram |
| Fig 2 data flow | p. 4 | p. 6 | Broken diagram; 2 pages late |
| Fig 3 FE bars | p. 10 | p. 11 | Missing V-D1; axis crushed by B0 |
| Tab 8 sweep | p. 13 | p. 13 top | Floats *before* §7.4 |
| Fig 5 labels | p. 14 | p. 14 top | Floats before §7.5 |
| Fig 6 reliability | p. 15 | p. 17 | Empty; non-primary; 2 pages late |
| Fig 7 risk–coverage | p. 15 | p. 18 | Color collision; incomparable rules |
| Tab 12 cost | p. 15 | p. 18 | Mixed splits |
| Fig 8 accuracy–cost | p. 15 | p. 19 | Per-call axis; 4 pages late |
| Tab 13 failures | p. 16 | p. 19 | Duplicates Fig 9 / Tab 7 |
| Fig 9 failures | p. 16 | p. 20 (Ethics) | Best figure, worst placement |
| Tab 14 cases | p. 16 | p. 22 | OK in appendix |

No table overflows the text block. The problems are emptiness, disconnection, missing bars, and floats in the wrong section.

---

## 2. Prioritized findings

### Critical

**C1. Abstract and intro bullet 3 contradict Table 7 / Figure 9 on where the cost lands.**

- Abstract p. 1 (`main.tex` 72–75; `main.txt` 19–21): “the cost appears as withheld contradictions.”
- Intro bullet 3, p. 2 (`main.tex` 147–152; `main.txt` 69–72): “the cost lands on contradiction rather than on support: REFUTE recall falls in all four models while SUPPORT recall barely moves.”
- Same abstract, two sentences earlier (`main.tex` 69–70): “it finds only 43% of supported claims, compared with 57% for the baseline.”
- Table 7 / `t7_per_class.tex` (p. 12), Luna development:

  | | SUPPORT R | SUPPORT FN | REFUTE R | REFUTE FN |
  |---|---|---|---|---|
  | B2 | 0.573 | 50 | 0.790 | 13 |
  | V | 0.427 | **67** | 0.597 | **25** |

  Macros: `\lunadevBTwosupportRecall{0.573}`, `\lunadevVsupportRecall{0.427}`. Additional misses: +17 support, +12 contradiction. V’s own errors are 67 missed support vs 25 missed contradictions (Table 13 / Fig 9). MiniMax V: 36 vs 9. Held-out V: 67 vs 31.

- The “withheld contradictions / SUPPORT barely moves” sentence is true only on the **30-claim sweep** (Table 8: SUPPORT unchanged on 3/4 models, −1 claim on Astra; REFUTE 0.8–0.9 → 0.5 on all four). Framing it as a paper-level finding, in the abstract and as one of “three findings [that] frame the result,” is a headline error.

**Rewrite (abstract sentence):** delete “and the cost appears as withheld contradictions.” Replace with: “On the full sample the coverage cost is missed support (SUPPORT recall 0.573→0.427; 67 missed supported claims vs 25 missed contradictions). A 30-claim sweep of four GPT-line models instead concentrates recall loss on REFUTE; that subset pattern does not match Table 7.”

**Rewrite (intro bullet 3):** “A 30-claim, four-model sweep (all closed-weight, same vendor lineage, including the primary model) does not raise false endorsement. REFUTE recall falls on every row; SUPPORT recall is unchanged on three rows. This is a subset direction, not the full-sample class breakdown, where SUPPORT recall drops 0.573→0.427.”

---

**C2. “Replicate across four models” overstates a same-lineage, same-vendor subset that includes the primary model.**

- Abstract (`main.tex` 72–74): “We replicate the comparison with a MiniMax family and on a frozen thirty-claim subset with four models, all closed-weight.”
- Macros: `\sweepModels{4}`, `\sweepClosed{4}`, `\sweepOpen{0}`, `\sweepAdditionalList{GPT-6 Astra, GPT-6 Sol and GPT-5.6 Terra}`. Table 8 rows are Astra, Sol, Terra, **Luna**.
- MiniMax is a second vendor on the *full* sample and is **not** in the sweep. The sweep is three GPT-6/5.6 variants plus the model already reported in Tables 3–7.
- Ethics p. 20 (`main.tex` 1210–1211): “the MiniMax family and for the **open-weight rows of the sweep**.” There are no open-weight rows (`\sweepOpen{0}`).

**Rewrite:** “We repeat the pairing with a second hosted model (MiniMax M3.1 Flash) on the 300-claim development sample, and with three additional closed-weight models from the same vendor lineage as Luna on a frozen 30-claim subset. MiniMax is not in the sweep; Luna is not a held-out replicate of itself.”

**Rewrite (ethics):** “the MiniMax condition, which ran inside an interactive agent runtime.”

---

**C3. “Family” is used for single models.**

- Throughout: “Luna family”, “MiniMax family”, “two model families”, “model-family transfer” (§5.3, §7.3, conclusion). Each “family” is one model (`GPT-6 Luna`, `MiniMax M3.1 Flash`). “Family” is also used correctly for cited-document clusters (`\lunadevnfamilies{246}`).
- 42 occurrences of “family” in `main.tex`. Reviewers will read this as inflating N.

**Rewrite:** “model” for Luna / MiniMax; “cited-document cluster” for the bootstrap groups; “vendor lineage” for the GPT sweep. Section title §7.3: “Transfer to a second model.”

---

**C4. Title says “Multi-Agent Validator System”; the paper describes staged stateless calls to one model.**

- Title and `pdftitle` (`main.tex` 27, 46–47).
- Body, p. 4 (`main.tex` 310–314): “Roles are isolated functions with typed inputs; several roles may call the same underlying model in separate stateless requests. Separate roles do not imply statistically independent errors.”
- Evaluation never exercises the proposer, the second retrieval round, or the renderer (Table 1 steps 1, 2-round gatherer, 7). SciFact claims are supplied, not proposed (`main.tex` 1149–1155).

**Recommended titles (pick one):**

1. **Independent Retrieval Does Not Reduce False Endorsement on SciFact** (preferred; matches RQ1 and the null)
2. Conservatism without Accuracy: Staged Reconciliation for Scientific Claims
3. Scope Disagreement, Not Missing Evidence: A Negative Result on SciFact

Do not keep “Multi-Agent” unless you run distinct models per role and measure independence.

---

**C5. RQ1 promises a matched inference budget; the paper never runs one, and V costs ~6× B2.**

- RQ1 p. 4 (`main.tex` 294–296): “At a **matched inference budget**, does independent retrieval plus staged evidence-first judgment reduce false endorsement…?”
- Limitations p. 19 (`main.tex` 1184–1189): “**No matched-budget control was run.** V spends several times the tokens of B2.”
- Table 12 / macros: B2 2×605 = 1,210 tokens/claim; V 3×2,598 = 7,794; ratio 6.4. V also 12.5 s vs 2.6 s median per call.
- §5.3 (`main.tex` 469): Luna is “the model behind the **powered** comparison” — but the primary interval includes zero and is driven by 2 vs 0 events (Table 13: B2 2 false endorsements, V 0).

**Rewrite RQ1:** “Does independent retrieval plus staged evidence-first judgment reduce false endorsement relative to same-evidence checking, at the (unmatched) call budgets of each design?” Add one sentence in §6.3: “V uses three calls and about six times B2’s tokens; a matched-budget B2@k control was planned and not run.”

---

**C6. Mechanism paragraph reverses comparison order and overstates “inherits the baseline’s accuracy.”**

- p. 14–15, `main.tex` 906–913 / `main.txt` 781–785:
  - Luna-dev: “0.838 against 0.838” (**B2 then V**)
  - held-out: “0.842 against 0.871” (**V then B2**)
  - MiniMax: “0.925 against 0.911” (**V then B2**)
- Intro bullet 1 (`main.tex` 139–140): “When the two scopes agree, V inherits the baseline’s accuracy.” Held-out agree: V 0.842 vs B2 0.871 (Table 9). MiniMax agree: V 0.925 vs B2 0.911. Not inheritance.
- Differ-slice V accuracy (0.443 / 0.366 / 0.593) is the gold-NEI rate by construction (`V NEI = 1.000`). Reporting it as a finding is circular.

**Rewrite:** “On development, when scopes agree (n=185), V and B2 both reach 0.838. On held-out agree (n=139), V is 0.842 against B2 0.871; on MiniMax agree (n=214), V is 0.925 against B2 0.911. When scopes differ, V abstains on every claim by construction, so its accuracy equals the gold-NEI rate; B2 remains correct on 0.600 / 0.642 / 0.767 of those claims.”

---

**C7. “Independent retrieval introduces documents the claim was never calibrated against” is not what Table 10 measures.**

- Factorial, p. 11 (`main.tex` 731–732): “Independent retrieval introduces documents that the original claim was never calibrated against, and it does not buy accuracy.”
- Table 10 / macros: unique yield **0.000**, annotated-not-cited **0**, overlap 0.096, unjudged 0.926, recall@k 0.849. Gold documents are a **subset of the cited documents**. D1 cannot repair a wrong citation on this corpus — the paper later says exactly that (`main.tex` 949–956).
- Held-out V-D1 FE is **0.032 vs B2 0.017** (`t1_heldout300.tex`) — the independent arm endorses *more* falsely — and this number is never stated in §7.2.

**Rewrite:** “On SciFact, every gold rationale document is already among the cited documents (unique yield 0.00). D1 mostly adds unannotated abstracts (92.6% unjudged). That is a property of the benchmark, not a finding that retrieval is ‘not the bottleneck.’ On held-out, V-D1 false endorsement is 0.032 against B2 0.017.”

---

### Major

**M1. “Strongest same-evidence configuration” is B1 on the scored metrics, not B2.**

- Intro p. 2 (`main.tex` 114–116): B2 “is the strongest same-evidence configuration we could build without training.”
- Table 3: B1 micro-F1 **0.843**, FE 0.044, SUPPORT R 0.829; B2 0.747 / 0.011 / 0.573; oracle O 0.870 / 0.005 / 0.769. B1 is close to the gold-rationale ceiling and *beats* the oracle on SUPPORT recall.
- The comparison to B2 is defensible as an evidence-first control, not as the strongest control.

**Rewrite:** “B2 is the evidence-first, same-evidence control that matches V’s reading policy. The stronger same-evidence condition is B1 (micro-F1 0.843 vs B2 0.747), which we report in Table 3 but do not use as the primary contrast.”

---

**M2. MiniMax V does not “make no such endorsement.”**

- Abstract (`main.tex` 67–69) is Luna-dev only (FE 0.000) and is easy to read as the system result.
- MiniMax V FE = **0.016** (3 false endorsements, Table 13); B2 = 0.033. “False endorsement never rises” is true; “makes no such endorsement” is not.

**Rewrite:** “On Luna-dev, V records 0 false endorsements against B2’s 0.011 (2 claims). MiniMax V still records 0.016 (3 claims).”

---

**M3. Limitations, no-human-study, and fail-closed caveats are repeated until they dominate the paper.**

Counted in `main.tex`:

| Caveat | Where it appears |
|---|---|
| No human study / no participant | Intro 155–156; RQ3 300–302; Discussion 1132–1135; Limitations 1193; Ethics; Appendix D (full protocol) |
| Four-way not scored | Intro 156–158; §3.2 285–289 (“We say this once here and repeat it”); Fig 5 caption; Limitations 1141–1144 |
| MiniMax endpoint withdrawn | §5.3; §7.3; cost caption; Limitations 1174–1180; Ethics 1213–1216; Appendix F |
| Fail-closed / retry | §5.4; Table 3 caption; Table 5; held-out prose; Limitations |
| Family / unmatched models | §5.3; §7.3; Limitations 1159–1163 |

This is defensive tone. An ACL reviewer will say: one Limitations paragraph, one sentence in the abstract, stop.

**Rewrite plan:** keep §3.2’s four-way mapping and §9 as the single caveats list. Delete the intro limitations paragraph (155–161), cut Appendix D to a pointer, mention the withdrawn endpoint once.

---

**M4. Generated held-out tables exist and are not in the paper.**

- `t1_heldout300.tex`: B2 n=300 F1 0.760 FE 0.017 SUPPORT R 0.581; V n=262 F1 0.618 FE 0.000 SUPPORT R 0.368; V-D1 FE **0.032**.
- `t1b_heldout300_paired.tex`: ΔFE −0.013 [−0.033, 0.000], n paired 262.
- 38/300 = 12.7% fail-closed on the freeze run is a reliability result, not a footnote.

**Rewrite:** promote a compact held-out table (or a held-out block inside Table 3). State V-D1’s higher FE. State that fail-closed cause is not broken out (transport vs parse).

---

**M5. Holm adjustment is claimed and never shown.**

- §6.4 (`main.tex` 620): “Secondary comparisons within a declared family are Holm-adjusted.”
- No Holm-adjusted number appears in any table.

**Rewrite:** drop the sentence, or add the adjusted p-values. Do not advertise a correction you do not report.

---

**M6. Figure / table consolidation (see also §4).**

Must-drop or appendix:

- Figure 6 (reliability) — empty, non-primary.
- Figure 1 *or* Figure 2 — merge into one correct diagram.
- Table 6 — merge into Table 3.
- Table 13 — keep Figure 9 next to Table 7; move the full taxonomy to appendix.
- Figure 3 — fix or drop (Table 3 already has FE).
- Figure 7 — appendix, or one V-vs-B2 curve with a single acceptance rule.
- Table 11 + Figure 6 — appendix only.
- Appendix D — cut hard.

Must-move next to their claim:

- Figure 9 beside Table 7 / the abstract claim about cost.
- Table 8 after the first paragraph of §7.4, with Luna marked “primary model, not a replicate.”

---

**M7. “Usable operating point” is asserted, not shown for a reader-facing tool.**

- Intro bullet 2 (`main.tex` 142–146) and Discussion (`main.tex` 1117–1121): “reported as a precision–coverage trade-off it is a usable operating point.”
- No human study. Figure 7 does not isolate V’s rule cleanly. SUPPORT precision 1.000 is real; coverage is 50/117 supported claims found, plus 38 held-out execution failures.

**Rewrite:** “V is a high-precision, low-recall operating point (SUPPORT P 1.000, R 0.427 on Luna-dev). Whether that is usable is out of scope; we did not test readers.”

---

**M8. Cost figure and table are easy to misread.**

- Table 12 mixes held-out V with dev B2.
- Figure 8 is per-call, not per-claim.
- Prose “roughly six times” is the right number if you multiply calls × tokens; the figure does not.

**Rewrite caption (Fig 8):** “X-axis is prompt tokens **per call**, not per claim. V issues 3 calls (≈7.8k tokens/claim) against B2’s 2 (≈1.2k). Points are not a matched budget.”

---

**M9. Several designed roles are described as if they were evaluated.**

- Table 1 / §4: proposer, second retrieval round, renderer, citation adequacy ratings.
- Evaluation: SciFact crowd claims, one retrieval budget, scored three-way labels. Adequacy ratings are never tabulated.

**Rewrite:** move unevaluated roles to a “designed but not scored” appendix box. Keep scored roles (reader, judge, auditor, reconciler) in the main figure.

---

**M10. Writing is long, systems-heavy, and one-column A4.**

- Class: `article` 11pt A4, 1-inch margins — not `acl`. 20 pages of main matter + 5 of appendix/refs.
- ~9,250 words before `\appendix`. A typical 8-page ACL long paper is ~4–5.5k words plus figures. Even after switching to two-column ACL style, this content is ~13–15 pages.
- §5 Implementation (records, hashes, retry, prompt contracts) is a reproducibility appendix, not Results.
- Related work (§2) is mostly “we do not reproduce X / we do not claim Y.”

**Cut list to reach ~8 pages + refs:**

| Keep in 8 pages | Move to appendix | Delete |
|---|---|---|
| Intro (cut to 1 col), RQ1–2, design (one figure + Table 1), setup, Tables 3+4+7+9+10, Fig 9, short discussion, short limitations | §5 Implementation, calibration, cost raw table, cases, prompts, reproduction, residual related work | Fig 6, Appendix D protocol, duplicate Table 6, Artifact blurb, intro limitations paragraph, most of Ethics paragraph 3 |

---

### Minor

**m1.** `Safe` → **SAFE** (`main.tex` 197).

**m2.** “p is the bootstrap probability mass on the side that excludes zero” (Table 4 caption). Non-standard; values 0.47 / 0.52 / 0.44. Either define it in one sentence in §6.4 or drop the column. A 95% CI that includes 0 is enough.

**m3.** Rounding: Table 10 `0.849` vs macro `0.85`; `0.096` vs `0.10`; `0.926` vs `93`. Generate the table from the same macros as the prose.

**m4.** Oracle SUPPORT recall (0.769) is *below* B1 (0.829) and is never discussed. One sentence: “Gold rationales do not raise SUPPORT recall above the claim-visible D0 judge.”

**m5.** “Cited-document family” vs “model family” vs “Luna family” — pick three different words.

**m6.** Figure 4 FE panel is four overlapping dots at 0. Drop that panel.

**m7.** Table 8 caption “a positive value means V endorses more” — every ΔFE is `+0.000 [0.000, 0.000]`. Say so.

**m8.** Bibliography: check unused entries; 2026 `@misc` items need stable URLs or “unpublished” labels.

**m9.** Hyphenat/`\emergencystretch` hide overfull boxes; after switching to `acl`, re-check line breaks.

**m10.** Conclusion (`main.tex` 1228–1230): “contradictions are withheld, endorsements are not gained.” Second clause is true (SUPPORT recall falls). First clause is the sweep story. Rewrite: “On the full sample V withholds both support and contradiction, more of the former; on the 30-claim GPT sweep the visible loss is REFUTE recall.”

---

## 3. Claim-by-claim audit (abstract, intro bullets, discussion, conclusion)

Numbers from `macros.tex` / generated tables. “OK” means the sentence matches those numbers.

| Claim | Where | Numbers | Verdict |
|---|---|---|---|
| B2 endorses ~1 in 100 non-support | Abstract | `\lunadevBTwofe{0.011}` | OK |
| V makes no such endorsement | Abstract | Luna-dev `\lunadevVfe{0.000}`; MiniMax 0.016; MiniMax 3 FEs | Overclaim if read as the system |
| V finds 43% of supported claims vs 57% B2 | Abstract | 0.427, 0.573 | OK |
| Held-out same trade-off; 38 fail-closed | Abstract | `\lunaheldVfailclosed{38}`; SUPPORT R 0.581→0.368 (scored) / 0.315 (all rows) | OK; all-rows 0.315 should be stated |
| Reduction not statistically significant | Abstract | Δ −0.011 [−0.029, 0.000]; held −0.013 [−0.033, 0.000]; MiniMax −0.016 [−0.046, 0.011] | OK |
| Replicate with a MiniMax family | Abstract | One MiniMax model, full factorial incomplete | Wording (C3) |
| Four models, all closed-weight | Abstract | 4 GPT-line, includes Luna, 0 open | Overclaim (C2) |
| Cost appears as withheld contradictions | Abstract | Full sample: 67 vs 25; sweep: REFUTE drops | **Contradicts Table 7** (C1) |
| Every gold doc already cited | Abstract | unique yield 0.000 | OK |
| Misses more supported claims | Abstract last sentence | SUPPORT R down in Luna, MiniMax, held-out | OK — keep this, delete the sweep sentence |
| B2 is the strongest same-evidence config | Intro | B1 F1 0.843 > B2 0.747 | Overclaim (M1) |
| Primary interval includes 0 | Intro | matches macros | OK |
| SUPPORT 0.573→0.427; 38 fail-closed | Intro | matches | OK — then bullet 3 undoes it |
| Independent retrieval is not the bottleneck | Intro bullet 1 | unique yield 0; benchmark property | Overclaim (C7) |
| V inherits B2 accuracy when scopes agree | Intro bullet 1 | held-out 0.842 vs 0.871 | Overclaim (C6) |
| Precision–coverage is a usable operating point | Intro bullet 2 | no user study; R 0.427 | Hedging that reads as a result (M7) |
| Cost lands on contradiction; SUPPORT barely moves | Intro bullet 3 | sweep only | **Contradicts Table 7** (C1) |
| Independent retrieval not sufficient; 3 CIs include 0 | Discussion | 3 comparisons | OK |
| Staging trades recall for precision | Discussion | P 0.971→1.000, R 0.573→0.427 | OK |
| Main obstacle is disagreement, not missing evidence | Discussion | 115/211 NEI are conflicts; unique yield 0 | Half benchmark artifact (C7) |
| Two model families; contradictions withheld, endorsements not gained | Conclusion | two models; full-sample missed support dominates | Overclaim (C2, C1, C3) |
| Open-weight rows of the sweep | Ethics | `\sweepOpen{0}` | **False** (C2) |
| Matched inference budget | RQ1 | no control; 6.4× tokens | **Inconsistent** (C5) |
| Holm-adjusted secondaries | §6.4 | none reported | Unsupported (M5) |
| Powered comparison | §5.3 | 2 vs 0 events | Misleading (C5) |

---

## 4. Figure / table inventory and consolidation

All `\ref` targets in `main.tex` are defined. Two generated tables are never included.

| ID | File | Referenced? | Discussed? | Action |
|---|---|---|---|---|
| Fig 1 architecture | architecture.pdf | yes | yes | Redraw or drop; merge with Fig 2 |
| Fig 2 data flow | data_flow.pdf | yes | one sentence | Merge into Fig 1 |
| Fig 3 FE bars | false_endorsement.pdf | yes | yes | **Fix V-D1** or drop; rescale |
| Fig 4 sweep | model_sweep.pdf | yes | yes | Drop FE panel; mark Luna as primary |
| Fig 5 labels | label_distribution.pdf | yes | yes | Keep; add held-out or leave |
| Fig 6 reliability | reliability.pdf | yes | caption disclaims it | **Drop** |
| Fig 7 risk–coverage | risk_coverage.pdf | yes | one sentence | Appendix, or one rule |
| Fig 8 accuracy–cost | accuracy_cost.pdf | yes | one sentence | Relabel as per-claim or drop |
| Fig 9 failures | failure_breakdown.pdf | yes | far from text | **Move next to Table 7** |
| Tab 1 pipeline | inline | yes | yes | Keep |
| Tab 2 conditions | inline | yes | yes | Keep |
| Tab 3 main-dev | t1_dev300.tex | yes | yes | Keep; add held-out block |
| Tab 4 paired-dev | t1b_dev300_paired.tex | yes | yes | Keep; add held-out row from unused file |
| Tab 5 sensitivity | t1c_sensitivity.tex | yes | yes | Appendix if short on pages |
| Tab 6 ablation | t2_ablation.tex | yes | yes | **Merge into Tab 3** |
| Tab 7 per-class | t7_per_class.tex | yes | yes | Keep; this is the result |
| Tab 8 sweep | t10_sweep.tex | yes | yes | Keep; annotate lineage |
| Tab 9 mechanism | t9_mechanism.tex | yes | yes | Keep; fix prose order |
| Tab 10 retrieval | t5_retrieval.tex | yes | yes | Keep |
| Tab 11 calibration | t4_calibration.tex | yes | yes | Appendix |
| Tab 12 cost | t3_cost.tex | yes | yes | Appendix or one row B2 vs V |
| Tab 13 failures | t6_failures.tex | yes | yes | Appendix; Fig 9 stays |
| Tab 14 cases | t8_cases.tex | yes | yes | Appendix (already) |
| — | t1_heldout300.tex | **no** | prose only | **Include** |
| — | t1b_heldout300_paired.tex | **no** | prose only | **Include** |

---

## 5. Writing quality (ACL/EMNLP reviewer notes)

- **Tone.** The paper argues with an imagined hostile reviewer in the main text (“we do not claim”, “we did not measure”, “reported but not scored”, “the subset is small and we read it that way”). That belongs in Limitations once.
- **Unclear terms.** “Family”, “powered comparison”, “local held-out”, “fail-closed”, “sealed reader”, “cited-document family”, bootstrap “p”. Define once in a glossary-like paragraph or drop.
- **Over-long sections.** §5 Implementation and §2 Related Work are the first cuts. §7.4 (sweep) is longer than the primary comparison.
- **Self-contradiction as structure.** Abstract paragraph 2 states the SUPPORT-recall drop, then attributes cost to contradictions, then closes with “misses more supported claims.” Three consecutive readings of the same experiment.
- **Page budget.** 25 A4 single-column pages, 20 of main matter. Target venue 8 pages + unlimited references. After converting to `acl` two-column, expect ~13–15 pages before cuts. Need to remove ~40–50% of main-matter words and 4–5 floats (list in M10).
- **Current abstract 254 words.** Rewrite below is 189.

---

## 6. Recommended title and abstract

**Title.** Independent Retrieval Does Not Reduce False Endorsement on SciFact

**Abstract (189 words), aligned to `macros.tex`:**

False endorsement—predicting SUPPORT when gold is not support—is costly in scientific claim checking. We test whether a staged pipeline that reconciles original citations (D0) with independently retrieved abstracts (D1) reduces it relative to a same-evidence evidence-first baseline (B2). Four isolated, fail-closed roles run as stateless calls to one model.

On 300 SciFact development claims (GPT-6 Luna), B2 false-endorsement is 0.011 and the validator (V) reaches 0.000, but the paired difference (−0.011, 95% CI [−0.029, 0.000]) includes zero. SUPPORT recall falls from 0.573 to 0.427 (67 missed supported claims vs 25 missed contradictions); micro-F1 falls from 0.747 to 0.687. A 300-claim held-out run repeats the trade-off; 38 V requests fail closed. MiniMax M3.1 Flash moves in the same direction (FE 0.033→0.016; SUPPORT recall 0.855→0.692), again with an interval covering zero. A 30-claim sweep of four closed-weight models from one vendor lineage, including the primary model, drops REFUTE recall; that subset pattern does not match the full-sample class breakdown.

Independent retrieval finds no annotated document that was not already cited (unique yield 0.00). Most V errors are D0/D1 disagreements resolved as underdetermined. V is more conservative, not more accurate.

---

## 7. Suggested fix order

1. Rewrite title, abstract, intro bullet 3, conclusion, and ethics “open-weight” sentence so they quote Table 7 / Figure 9, not the 30-claim sweep (C1, C2, C4).
2. Redraw one architecture figure; delete the other; delete Figure 6; move Figure 9 to §7.1 (C4, M6).
3. Fix Figure 3 (show V-D1 or drop); `\input` the held-out tables; merge Tables 3 and 6 (M4, M6).
4. Replace “family” / “four-model replication” / “matched budget” / “strongest baseline” wording (C2, C3, C5, M1).
5. Cut §5, the intro limitations paragraph, Appendix D, and repeated MiniMax-withdrawn passages so the paper can become an 8-page ACL submission (M3, M10).
