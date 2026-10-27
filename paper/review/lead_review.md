# Lead reviewer notes (first pass, before subagent reports)

## Critical
1. **Headline contradicts the main table.** Abstract ("the cost appears as withheld
   contradictions") and intro bullet 3 ("SUPPORT recall barely moves") come from the
   30-claim sweep. On the full dev sample V loses 67 supported claims vs 25 refuted
   (t7: SUPPORT R 0.573 -> 0.427, REFUTE R 0.790 -> 0.597). The abstract's own
   first paragraph says 43% vs 57% support recall. Self-contradictory.
2. **The benchmark cannot test the hypothesis.** Unique yield = 0 because SciFact
   gold docs are a subset of cited docs. RQ1's motivating failure (wrong citation)
   never occurs in the data, so "independent retrieval is not the bottleneck" is
   not a finding, it is a property of the test bed. Needs either a citation-
   corruption experiment or reframing of every mechanism claim.
3. **Primary test has ~no power.** B2 makes 2 false endorsements out of 183 gold
   non-support claims (dev), 3 on held-out. Max detectable reduction is 2 events;
   an exact McNemar on 2-vs-0 discordant pairs gives p = 0.5. The claim "the full
   sample was sized for the one-point false-endorsement rate" has no power analysis
   behind it. Percentile bootstrap with V at exactly 0 FE is degenerate (upper
   bound pinned at 0). The "p" column is non-standard.
4. **2x2 factorial is confounded.** Per the appendix contracts, B2's compare step
   sees claim + sealed record and emits 3-way labels; V's judge sees claim + sealed
   record + passages and emits 4-way labels. V-D1 is derived from V, not run.
   "Reading policy" and "evidence access" are not the only differences.

## Major
5. "Preregistered" without a public timestamped registration; dev numbers changed
   after a retry policy was introduced (RESULTS.md: 32 dev fail-closed, B2 SUPPORT
   R 0.530, 226 families, T=1.8; paper: 0, 0.573, 246, T=0.4). Baselines appear
   re-run. Either document the change history or call it "pre-specified".
6. Held-out: 38/300 (12.7%) V fail-closed, cause not reported; V-D1 FE on held-out
   is 0.032 > B2 0.017 (independent arm endorses *more* falsely) and is never
   mentioned.
7. Cross-model "replication" = 4 closed models from one vendor lineage, one of
   which is the primary model, on 30 claims (FE denominator 20). Abstract overstates.
8. "Family" used for single models; title "Multi-Agent" for a staged pipeline of
   stateless calls to one model.
9. Model identifiers (GPT-6 Luna, MiniMax M3.1 Flash, ...) lack versions/dates;
   MiniMax served by a withdrawn free endpoint -> not reproducible.
10. No matched-budget control although planned (B2@k, k=7) and cheap.
11. Conflict definition: d0_d1_conflict fires when four-way labels differ, which may
    include unaddressed-vs-underdetermined (both NEI). Need to check; if so the
    "disagreement detector" story is inflated.
12. Calibration reported in-sample on the calibration split; only for B1, which is
    not a primary condition. Risk-coverage compares different acceptance rules.
13. Cost table mixes splits (V tokens from held-out run, B2 from dev).
14. Holm adjustment is claimed but no adjusted result is reported.
15. SciFact metrics: label-only accuracy, not official abstract/sentence-level
    metrics; not comparable to SciFact leaderboard, should be stated. Pretraining
    contamination of SciFact not discussed (B0 = 0.547 micro-F1 from prior alone).
16. Proposer, second retrieval round, renderer are described but never exercised
    by the evaluation.

## Minor
- Ordering inconsistency in mechanism paragraph (B2-vs-V then V-vs-B2).
- "Safe" -> SAFE. Unused bib entries. Four 2026 @misc refs need IDs.
- No author block. Font warnings from hyphenat[htt].
- Limitations repeated in intro, sections 7.x, limitations, ethics.
- paper/RESULTS.md stale vs paper.
