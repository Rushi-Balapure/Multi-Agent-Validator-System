# Implementation plan: Multi-Agent-Validator-System

Source of scope: [Validator_Agent_Two_Month_Research_Plan.pdf](../Validator_Agent_Two_Month_Research_Plan.pdf). Planning sizes, thresholds, and costs in that document are proposed choices, not completed results. This file sequences repository work. It does not add research claims.

## Goal

Reproducible inference-time validator + paper draft. SciFact first. Baseline (same-evidence) before validator (independent retrieval + staged judgment).

The validator checks scientific conclusions from an upstream agent, separates support in the original citations (D0) from independently retrieved evidence (D1), and explains uncertainty to a non-expert reader. The task is interpreting research evidence in biomedical abstracts, not giving treatment advice. Start with a frozen local corpus and replaceable local model endpoints.

By the research plan, week 2 delivers the same-evidence baseline, corpus index, schemas, and locked split manifest. Later weeks add independent retrieval, staged judgment, locked experiments, and the paper draft. A positive result, publication acceptance, or a conclusive human study is not a completion criterion.

## Phase 0 — Repo contracts

- Python, typed schemas, CLI runner, local retrieval index, replaceable inference client
- Layout: src/validator/, src/evaluation/, configs/, prompts/, data/, tests/, paper/, docs/paper-assets/
- Records: Run, Claim, Evidence, Judgment, Report verdict (fields as in research plan §4)
- Reproducibility: results file + immutable traces; cache by normalized inputs; one command each for index / validate / tables

Deferred until the batch runner is reliable: a small FastAPI endpoint. The study interface, when it exists, is an HTML template. A large frontend or agent framework is out of scope.

Suggested module split from the research plan (created in later slices, not in the scaffold):

- `src/validator/`: `schemas.py`, `decompose.py`, `retrieve.py`, `evidence_reader.py`, `judge.py`, `reconcile.py`, `calibrate.py`, `render.py`, `runner.py`
- `src/evaluation/`: `adapters.py`, `metrics.py`, `bootstrap.py`, `study_analysis.py`
- `configs/`: model, corpus, and experiment YAML
- `prompts/`: versioned role templates
- `data/`: manifests and permitted data; source text kept separate from labels
- `tests/`: contract, isolation, and regression cases
- `paper/`: section drafts, references, figures, and appendices
- `docs/paper-assets/`: metric graphs and formula notes for the paper

Record fields (research plan §4):

- **Run:** `run_id`, `question_id`, `split`, `seed`, `model_id`/revision, `prompt_hash`, `corpus_hash`, `config_hash`, timestamps, tokens, status
- **Claim:** `claim_id`, `report_id`, exact source span, normalized claim, subject, relation, object, population, comparator, time, units, modality, neutral question, asserted answer, dependencies
- **Evidence:** `doc_id`, DOI/PMID if present, snapshot hash, text span and offsets, query, rank, retrieval round, original/independent provenance, deduplication group, access scope
- **Judgment:** `claim_id`, evidence scope, label, rationale codes, cited span IDs, raw scores, calibrated probabilities if valid, execution status, uncertainty reasons
- **Report verdict:** claim coverage, central claim outcomes, inference-link status, conflicts between D0 and D1, display explanation, limitations

Execution status is separate from scientific labels. A timeout is an execution-failure status, never an evidence verdict.

Reproducibility contract from the research plan:

- Each completed run emits a machine-readable results file and an immutable trace.
- Cache by normalized input, model revision, prompt, corpus, seed, and retrieval settings. Include split in evaluation metadata. Caches must never expose labels or private evaluator pools to inference.
- Restart at the last completed component without mixing old and new configurations.
- One command indexes a supplied corpus. One command validates frozen reports. One command computes tables from saved predictions.
- Ship a tiny licensed example so reproduction can be checked without a GPU or live search.

## Phase 1 — Baseline (same-evidence)

Done when: working same-evidence checker on frozen SciFact corpus, schemas, locked split manifest, contract tests green.

Week-2 exit gate from the research plan: every submitted item has a prediction or an explicit failure record; no label leakage; native scoring works. Fix retrieval identifiers and data integrity before improving prompts.

Work units (each → one MR):

1. Schemas + pydantic models + fixtures
   - Typed Run, Claim, Evidence, Judgment, and Report verdict models with the §4 fields.
   - Execution status separated from the four scientific labels (Supported, Contradicted, Unaddressed, Underdetermined). Those labels are defined for later judgment; this slice only locks the schema.
   - Fixtures for numeric, negation, and population examples used by the same-evidence checks.
2. SciFact adapter + corpus index (BM25) + split manifest lock
   - Frozen SciFact abstract corpus. Begin with BM25. Preserve document identifiers, text offsets, corpus hashes, and original citations.
   - Data manifest: dataset version, retrieval date, license/access terms, counts, excluded IDs, grouping rules, hashes, and provenance.
   - Split discipline from the research plan: released training data for development and calibration; reserve a fixed calibration subset from the released training split before prompt tuning (example given in the plan: 100 claims if available after grouping); treat the public development split as a local held-out evaluation if official test labels are inaccessible, and name it accurately. Group duplicate claims, paraphrases, question families, and derivative reports in one split.
3. Same-evidence baseline runner (check claims against D0 citations only)
   - Judge claims against the original citation set D0 only. No independent retrieval in this phase.
   - Research-plan baselines in this family: B0 (direct judge sees report + D0), B1 (atomic claims + D0; judge sees asserted answers), B2 (neutral questions + isolated reader + D0, then compare). Adaptations are named as adaptations. A prompt-only condition is not labeled as a reproduction of a trained method.
   - Payload isolation for the factored D0 reader: blind inputs must not contain asserted answers.
   - Inference client: an OpenAI-compatible local-or-private-LAN endpoint (urllib; no cloud SDK). Default is LM Studio on this machine at `http://127.0.0.1:1234/v1` with model id `qwen2.5-coder-1.5b-instruct`. An RFC1918 address such as `http://192.168.1.10:1234/v1` is also allowed from another private-LAN host. Loopback remains valid for a local proxy. Public DNS names and non-private addresses are refused, including redirects.
4. Evaluation adapters + native SciFact metrics + bootstrap timers
   - Preserve official scorer inputs and outputs. Report native support / refute / evidence metrics.
   - Three-way insufficient-information labels are not gold four-way underdetermined labels. Any coarse mapping that collapses Unaddressed and Underdetermined into insufficient information is labeled as that comparison.
   - Bootstrap timers follow the research plan's statistics section: paired comparisons; bootstrap by question family (proposed default 2,000 resamples), carrying both generator reports and all their claims together when that set exists; public-benchmark resampling preserves source-document or question clusters where applicable. Latency and token fields on the Run record are the timers this slice records. Do not treat proposed sample sizes as measured results.
5. Tiny licensed example + smoke CLI
   - A small licensed example so the index, validate, and table commands can be checked without a GPU or live search.
   - Development smoke path from the research plan: a small development run that inspects invalid outputs, latency, tokens, and evidence recall. Contract tests cover schema-valid outputs or explicit failure records.

## Phase 2 — Validator approach

Done when: independent gatherer, evidence reader, judge, citation auditor, reconciler, renderer wired; staged pipeline runs on development budget defaults (≤8 claims/report, 2 retrieval rounds, 3 query forms, 8 passages).

Development defaults from the research plan, frozen before testing: at most 8 claims per report, 2 retrieval rounds per claim, 3 query forms per round, and 8 evidence passages in the judge context. If a report exceeds the claim budget, mark partial coverage and list unchecked spans. Round 2 runs only for unresolved questions, scope mismatch, or contradictory evidence. Stop on exhausted budget, no new eligible documents, or a complete bounded evidence record. Generate the report once, freeze it, and validate without an automatic rewrite loop in the main study.

Roles are isolated functions with typed inputs. Several roles may call the same model in separate stateless requests. Separate roles do not by themselves establish statistically independent errors.

Work units (each → one MR):

1. Neutral question / claim decomposition
   - Proposer inputs: question and frozen conclusion. Outputs: atomic claims, neutral questions, asserted answers, and source spans.
   - Preserve quantities, confidence language, population, experimental setting, and causal scope. Split a conjunction into separate claims and retain the relationship. Do not upgrade association to causation, drop a population qualifier, or remove a comparator. Mark opinions and recommendations separately. Map every claim back to exact report text.
2. Independent gatherer + retrieval protocol (open / scope / null-results queries)
   - Inputs: neutral question, scope, corpus. Output: fresh evidence D1. Hide the conclusion, asserted answer, original citations, and generator identity.
   - For each neutral question: an open inquiry, a scope/measurement query, and a limitations-or-null-results query. Retrieve top 20 candidates per query, deduplicate, rerank the union, and select up to 8 passages. Keep one document's adjacent context together when needed to resolve negation or units. Log missing metadata rather than inferring study design from an abstract.
   - Do not suppress D0 overlap in the main system. Report document overlap and unique evidence yield. An exclusion-of-D0 condition is only a labeled diagnostic. Deduplicate preprint/publication versions and repeated snippets.
   - Dense retrieval and reciprocal-rank fusion (`1 / (60 + rank)` summed across lists) are a development-data comparison, not the starting index. Live search is a dated stretch experiment, not the source of main-test labels.
3. Evidence reader (blind) then Judge (claim-visible) with four labels
   - Evidence reader: neutral question and shuffled D1. Output an evidence-only answer and cited spans. Seal that record before revealing the claim.
   - Judge: atomic claim, sealed record, and D1. Output an independent-evidence label and uncertainty. The final judge must see the claim. The blind stage is the preceding evidence-only reading. Neutral questions can still leak topic and assumptions; audit that leakage.
   - Labels, relative to a stated evidence collection and search budget: Supported, Contradicted, Unaddressed, Underdetermined. Decision order: execution and claim validity, then relevance; no addressing passage → Unaddressed; materially conflicting or inconclusive relevant evidence → Underdetermined; otherwise support or contradiction only at the preserved scope. A non-significant result is not automatically proof of no effect.
4. Citation auditor (D0) + Reconciler (D0 vs D1)
   - Citation auditor: atomic claim and D0. Separate original-citation label, spans, and citation defects.
   - Reconciler: the two judgments and claim dependencies. Explain differences, assess combined evidence, and flag invalid inference links.
   - Keep scope-specific outputs. D0: is the original citation set faithful? D1: what does independent retrieval establish? D0 ∪ D1: what can be said after reconciliation? Do not repair citation faithfulness with outside evidence. Multi-hop inference links are labeled valid, invalid, or unresolved. Supported premises do not prove a causal or transitive conclusion.
5. Renderer claim cards + calibration hooks (no test fitting)
   - Renderer input is the validated structured record. Output is plain-language claim cards and a cautious report summary. No new factual claims. Generate prose only from the structured record, then verify each explanatory assertion against stored spans.
   - Claim card fields from the research plan: claim; evidence verdict; why (linked excerpts with study scope); what is uncertain; search scope; original citations (adequate, inadequate, or unverifiable); next useful check.
   - Calibration hooks only. Prefer a constrained four-label classifier with class scores. Fit one temperature on the calibration split, minimizing multiclass negative log-likelihood, or a small regularized calibrator whose development choices are fixed in advance. Fit no parameters on test data. Public-benchmark and agentic-report calibration stay separate. If scores are insufficient, show qualitative uncertainty and report that numerical calibration is unvalidated. Abstention thresholds are chosen on calibration data. A scientific Underdetermined label and a model "defer to reviewer" action are separate fields.
6. Ablation/config flags for evidence access × information separation
   - Primary 2×2 from the research plan: evidence access (D0 versus independent retrieval) crossed with reading policy (claim-visible versus neutral-question, evidence-first). Hold decomposition, underlying model, and downstream label interface constant.
   - Config flags must name the condition (including B3 fresh retrieval + direct claim-aware judge, and the evidence-oracle diagnostic O). Run a natural-budget comparison and a matched total-token/call-budget comparison. Secondary ablations stay behind this factorial comparison and are not part of this slice's done-check.

## Phase 3 — Experiments + paper assets

- Locked main experiments, cost analysis, figure drafts under docs/paper-assets/graphs/
- Formula notes for cited metrics under docs/paper-assets/formulas/
- Hold create-verification-skill until baseline CLI actually runs

Locked experiments follow the research plan's week-5 freeze: code commit, prompts, corpus snapshot, and experiment configurations fixed before untouched evaluation. The preregistered primary comparison is V versus B2 for false endorsement on the custom held-out set. The factorial comparison interprets the mechanism. Report effect sizes and 95% intervals, including null results. Count infrastructure failures and show all-submitted-item results.

Cost analysis uses measured tokens, calls, latency (median and p95, warm and cold cache), failures, and peak memory. The research plan's token arithmetic is a sizing example to replace with measured totals, not a target.

Figure drafts (research plan, experiment ledger): architecture, reliability plot, risk-coverage curve, accuracy-cost trade-off, and failure breakdown. Tables T1–T5 are produced from saved predictions. Formula notes record the cited definitions (native SciFact scores, four-way macro-F1, false endorsement, Recall@k / Precision@k, multiclass Brier, NLL, ECE, selective risk) without fitting anything on test data.

`create-verification-skill` stays unbuilt until the baseline CLI from Phase 1 actually runs (index, same-evidence validate, and tables from saved predictions).

## MR rules

- One slice per MR; proper description + done-check
- Arch Lead verifies then merges to main
- No product invention beyond the research plan

Each merge request is one work unit above. The description states the slice, the research-plan section it implements, and the done-check (schema-valid outputs or explicit failure records, verified evidence links where that slice emits them, no known information-boundary leak for slices that touch role payloads, and reproducible scores from saved traces when evaluation is in scope). Do not change engineering acceptance criteria to chase a positive finding.

Arch Lead reviews the slice against this plan and the research-plan PDF, then merges to `main`. Do not add product surface, datasets, metrics, or agent roles that the research plan does not specify. Stretch items in the plan (SciFact-Open, Missci, live retrieval, extra model families, full MARCH training, the human study) stay out of the core MR sequence until the plan's cut order allows them.
