# Validator Agent: research plan, updated after the first measurement cycle

This file supersedes the two-month plan in
[`Validator_Agent_Two_Month_Research_Plan.pdf`](../Validator_Agent_Two_Month_Research_Plan.pdf)
as the working statement of scope. The original document remains the
reference for the research questions, the design constraints, and the
honesty rules; this file records what actually happened, what changed, and
what is still owed.

Everything here is a statement about work that was carried out or work that
is still open. No planned result is presented as a measured one.

## 1. What the original plan asked for, and what happened

The plan asked for an inference-time validator that checks scientific
conclusions produced by an upstream agent, separates the support in the
original citations (D0) from independently retrieved evidence (D1), and
explains uncertainty to a non-expert reader, together with a complete
research-paper draft within eight weeks.

| Plan item | Status | Where |
| --- | --- | --- |
| Frozen local corpus, locked split manifest, corpus hash | done | `data/pins/scifact/`, `manifests/scifact/` |
| Same-evidence baseline (B2) with isolated reader | done | `src/validator/same_evidence/` |
| Independent retrieval (BM25) with query variants | done | `src/validator/retrieval/` |
| Staged judgment: sealed reader, judge, citation auditor, reconciler | done | `src/validator/live_judgment.py`, `src/validator/reconcile.py` |
| Fail-closed execution semantics | done | `src/validator/schemas.py`, parsers in `live_judgment.py` |
| Preregistered primary comparison, paired cluster bootstrap | done | `src/evaluation/bootstrap.py`, `docs/freeze.json` |
| Locked held-out 300 run | done (one run) | `artifacts/held_out/` |
| Cost, latency, token accounting | done | `src/validator/usage.py`, Run record |
| Calibration on a reserved split | done | `scripts/paper/make_calibration.py` |
| Error taxonomy and manual sample | done | `scripts/paper/make_failure_taxonomy.py` |
| Independent model family | done | `tools/opencode_bridge.py`, second family in the paper tables |
| Retrieval-metric table (recall@k, D0/D1 overlap, unique yield) | done | `scripts/paper/make_retrieval_metrics.py` |
| Complete paper in arXiv format | done | `paper/main.tex` |
| **Custom agentic set with human four-way labels** | **not done** | see §4 |
| **Human trust-calibration study** | **not done** | see §5 |
| **Matched-token-budget control** | **not done** | see §6 |
| Dense retrieval and reciprocal-rank fusion as the product path | not done | prepared only |

## 2. The measurement that changed the plan

The preregistered primary comparison is null. On the development sample the
paired difference in false endorsement between the staged validator and the
same-evidence baseline is small and its interval includes zero; the held-out
sample reproduces the pattern. The staged validator does reach zero false
endorsement, but it reaches it by withholding support, and the mechanism
behind that behaviour is scope disagreement rather than better evidence.

Three plan assumptions did not survive contact with the data.

1. **"Independent retrieval will find evidence the original citations
   missed."** On SciFact it does not. The annotated document set is a subset
   of the cited document set, so a retriever that searches the same corpus
   cannot find new *gold* evidence; it adds unannotated context only (unique
   yield exactly 0.00, unjudged rate 0.93). A null result on this benchmark is
   therefore partly structural, and the paper says so.
2. **"Evidence-first reading will help."** It does not. Across both evidence
   scopes and both model families, the claim-visible judge scores higher
   than the neutral-question, evidence-first reader. Isolation is not free:
   the sealed reader withholds the claim that the judge needs.
3. **"The interesting result will be a new operating point."** It is, but it
   is a disagreement detector rather than an evidence-acquisition system.
   The paper frames the contribution as a negative result with a mechanism.

## 3. Deviations from the original protocol, and why

Each deviation is stated in the paper as well.

* **Second model family through an agent runtime.** The second family is
  reachable only through the OpenCode runtime, which has no OpenAI-compatible
  surface. `tools/opencode_bridge.py` exposes one on loopback, one fresh
  session per request. The harness prepends a fixed agent preamble to every
  request; it is identical across conditions, so it cancels in comparisons,
  but it inflates the reported prompt-token counts and is called out in the
  cost discussion.
* **Retry policy for failed executions.** A request that fails for
  transport or parse reasons is retried up to four times; the failed rows
  are dropped from the prediction file between attempts so that the resume
  re-claims exactly those claims. The policy is applied to every development
  run of every condition and every model family. The held-out run is the
  single execution it was always meant to be and predates the policy; the
  paper reports the fail-closed counts and an all-rows scoring variant so
  that the policy cannot hide hard cases.
* **Fail-closed rows are excluded from scored metrics and counted.** The
  paper additionally scores every submitted row with the label the method
  recorded (the conservative NEI), so a method cannot improve by failing.
* **Two labelled errors in the paper's own draft.** The previous draft
  referred to trained verifiers "KGAT" and "ARISTO". Neither title exists.
  They were removed, and every remaining reference was checked against the
  ACL Anthology, arXiv, PMLR, or the repository.

## 4. What is still owed: the agentic set

The plan's agentic track (40 research questions, 80 reports from two
generator families, human reference-claim inventories, double annotation
with adjudication) was not run. Without human labels there is no
four-way gold for agent-generated claims, and an LLM-generated gold would
measure the model against itself.

What exists instead is the SciFact-native evaluation: claims with
crowd-sourced annotations, a frozen corpus, locked splits, and a
preregistered primary comparison. That is a weaker but honest evaluation,
and the paper describes it as such.

The smallest honest version of the missing track, if it is ever run, needs:
a frozen set of 20 multi-hop research questions, a deterministic proposer
for atomic claims, at least two annotators with relevant training, a
written rubric, and adjudication. The rubric and the four-way decision order
already exist in the repository (`prompts/`, `src/validator/label_policy.py`)
and the study protocol is written out in the paper's appendix so that it can
be executed without redesign.

## 5. What is still owed: the human study

No participant was recruited, no ethics review was obtained, and no claim
about human benefit is made anywhere in the paper. The protocol (30
non-expert adults, 12 expert-reviewed items, three interface conditions,
counterbalanced assignment, mixed-effects analysis with a participant-level
fallback, a prespecified wrong-advice stratum) is in the appendix as a
protocol with no results. Running it requires institutional review, which is
outside the repository's reach.

## 6. What is still owed: the matched-budget control

V spends several times the tokens of B2 per claim, so compute remains a live
rival explanation for part of the F1 gap. The plan asked for a
token-matched self-consistency control (B2 at $k$ samples). It was not run:
the hosted free tier throttled bursts hard enough that the extra calls were
not affordable in the time available, and a partial control would have been
worse than none. The paper lists this as a limitation rather than
interpreting the gap as mechanism.

The control is cheap to add for the API family: repeat the B2 comparison
step with $k$ seeds at temperature above zero and vote, matching V's token
budget. It is the first experiment to run if the work continues.

## 7. Cut order if the schedule slips again

First remove the live-retrieval stretch benchmark, the extra ablations, and
the second model family. Then reduce the transfer sample size prospectively.
Preserve the primary factorial comparison, gold-label independence, failure
accounting, and evidence provenance. If the human study is infeasible, keep
the technical paper and the protocol and remove every claim of demonstrated
human benefit.

## 8. Definition of completion, unchanged

An honest, reproducible paper-ready package. A positive result, publication
acceptance, and a conclusive human study are not completion criteria. On the
current evidence the package is a negative result with a mechanism analysis,
a reproducible artifact, and two explicitly open obligations: the
matched-budget control and the human study.
