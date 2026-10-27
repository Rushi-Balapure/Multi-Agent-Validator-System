# Consolidated external review of `paper/main.pdf`

Sources: lead review (`lead_review.md`), opencode/DeepSeek V4.1 Flash referee
(`opencode_referee.md`, score 2/5 reject, confidence 4/5), Grok 4.6 methodology
(`grok_methodology.md`), Grok 4.6 related work (`grok_related_work.md`), Grok 4.6
presentation (`grok_presentation.md`). Every item marked **[verified]** was
re-computed by the lead reviewer from the saved prediction files or run sidecars.

Verdict as submitted: **not publishable at a peer-reviewed venue.** The data
support an honest, narrower paper; the current framing, statistics and
provenance statements do not.

## Critical

1. **Abstract and introduction contradict the main table.** "The cost appears as
   withheld contradictions" / "SUPPORT recall barely moves" come from a 30-claim
   sweep. Full sample: V misses 67 supported vs 25 refuted claims
   (SUPPORT R 0.573 -> 0.427). [verified, t7_per_class.tex]
2. **The primary test has no power.** Dev and held-out both reduce to 2 vs 0
   discordant pairs; exact McNemar p = 0.50 on each. Percentile bootstrap is pinned
   at 0 because V has zero FE; the reported "p" (0.47/0.52) is computed by a formula
   (`holm.py`) that does not match its caption and is invalid at Delta = 0. No
   power analysis exists; "sized for the one-point rate" is unsupported. [verified]
3. **SciFact cannot test the motivating mechanism.** Annotated docs are a subset of
   cited docs for 179/179 claims, so independent retrieval's unique yield is 0 by
   construction. No wrong-citation case exists in the data. [verified]
4. **"Preregistered" overstates the provenance.** No public registry. The freeze
   (`docs/freeze.json`, committed 2026-09-26) was built from completed dev
   sidecars after the dev null was known (RESULTS.md "Decision: null"). The dev V
   numbers in the paper come from an Oct 20 re-run (config `0c4a...`) that differs
   from the frozen config (`c3d7...`) used on held-out; B2 was re-run too and 26/300
   labels flipped. The original frozen-config dev run is still in
   `artifacts/validator_v_dev300` (32 fail-closed, SUPPORT R 0.383). [verified]
5. **The "disagreement detector" story is inflated and the detector is poor.**
   `d0_d1_conflict` fires on four-way inequality: 60/115 dev (73/123 held-out)
   "conflicts" are unaddressed-vs-underdetermined, i.e. both NEI. On genuine
   three-way conflicts V is right on 29% (dev) / 10% (held-out) of claims versus
   B2's 56% / 70%. [verified]

## Major

6. **Factorial is confounded.** B2's compare step sees claim + sealed record and
   emits 3-way labels; V's judge also sees passages and emits 4-way labels; V-D1 is
   derived from V, inheriting its 38 held-out failures. [verified in code by Grok]
7. **Unreported adverse result.** Held-out V-D1 false endorsement 5/156 = 0.032 vs
   B2 3/176 = 0.017: the independent-retrieval arm endorses *more* falsely. [verified]
8. **Held-out fail-closed rows are not random.** 38/300 failed; 18 are gold SUPPORT.
   The failure reason is overwritten by the reconciler, so timeout/parse/transport
   cannot be separated. [verified]
9. **Cross-model "replication".** Four closed models of one vendor lineage,
   including the primary model, on 30 dev claims; all Delta FE intervals are
   [0, 0]. Ethics section mentions "open-weight rows" that do not exist. [verified]
10. **No matched-budget control** although RQ1 says "at a matched inference
    budget" and `majority.py` implements B2@k. V costs about 6.4x B2's tokens; the
    cost table mixes held-out (V) and dev (B2) runs.
11. **Holm adjustment claimed but never reported** (family of one, JSON only).
12. **Calibration reported in-sample** (T fitted on the 100-claim split and
    evaluated on it); B1 only; "temperature 0" is not actually sent to the hosted
    API.
13. **Related work misses** SciFact SOTA (VeriSci, ParagraphJoint, ARSJoint,
    MultiVerS), MiniCheck, FActScore, ALCE, selective prediction (Chow; El-Yaniv &
    Wiener; Geifman & El-Yaniv), knowledge-conflict work (Xie et al. 2024;
    ClashEval). Numbers are claim-level 3-way, not official SciFact metrics.
14. **Terminology/title.** "Family" for single models; "Multi-Agent" for a staged
    pipeline of stateless calls to one model; "strongest baseline" while B1 beats
    B2 on micro-F1.
15. **Contamination / sampling.** B0 reaches SUPPORT R 0.863 from the claim alone;
    dev300 is sampled from SciFact train; 95 cited docs are shared between dev300
    and held-out.

## Presentation

- Architecture figure: citation auditor has no D0 input; arrow crosses its label.
- False-endorsement figure prints "n/a" for V-D1 although values exist; B0 bar
  flattens the plot.
- 25 pages, about 2x a typical 8-page limit; limitations repeated 4-6 times;
  empty author block; held-out tables generated but never included.
- `paper/RESULTS.md` is stale.

## What can be fixed without new model calls

- Reframe title/abstract/intro/discussion around what the data show.
- Replace bootstrap "p" with exact McNemar; report discordant counts; add a
  minimum-detectable-effect statement.
- Re-define conflict on the scored 3-way label and re-compute mechanism numbers.
- Reconciliation-rule ablation (trust D0, trust D1, 3-way conflict, any-support)
  from saved per-scope labels.
- Report the frozen-config dev run alongside the retry re-run; disclose timeline.
- Report held-out V-D1 FE; fail-closed by gold class.
- Fix figures, related work, terminology; cut length.

## What needs new runs (cost money / endpoint access)

- Citation-corruption experiment (swap D0 for non-gold abstracts) - the only test
  of the motivating hypothesis.
- B2@k matched-budget control.
- Matched-input factorial (give B2 the passages, or strip them from V's judge).
