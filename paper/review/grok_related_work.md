# External review: related work and bibliography

**Paper:** `paper/main.tex`  
**Bibliography:** `paper/references.bib`  
**Reviewer role:** external bibliography / related-work audit  
**Date:** 2026-10-27  
**Files edited:** none (this file only)

This audit verifies every existing BibTeX entry against ACL Anthology, arXiv, PMLR, NeurIPS proceedings, or GitHub; checks how `main.tex` describes each cited work; lists unused and missing keys; supplies reviewer-demanded missing related work with verified BibTeX; and positions the paper’s SciFact numbers against official SciFact metrics.

---

## Executive findings

1. **No fabricated citations.** Every `@misc` 2026 entry and the flagged 2024–2025 papers exist. Several 2026 preprints have since been published (MARCH at ACL 2026; Hirsch et al. at EMNLP 2026) and should be upgraded from `@misc` to `@inproceedings`.
2. **No missing citation keys.** Every `\citep{...}` key in `main.tex` is defined in `references.bib`.
3. **Three unused bib entries:** `zhang2024smallverifiers`, `kamoi2023wice`, `scifactdata`.
4. **Related work is the paper’s weakest section.** It cites recent LLM self-check / RAG-hallucination work but omits the SciFact pipeline literature a reviewer will demand (VeriSci, ParagraphJoint, ARSJoint, MultiVerS), the biomedical claim-verification datasets that sit next to SciFact (HealthVer, COVID-Fact, Check-COVID), the LLM fact-checking stack (FActScore, MiniCheck, LLM-as-a-judge), and the classical selective-prediction / knowledge-conflict / citation-attribution literatures that the discussion already depends on.
5. **Metric incomparability.** The paper reports claim-level three-way label accuracy / micro-F1. Official SciFact reports abstract-level Label-Only / Label+Rationale F1 and sentence-level Selection / Selection+Label F1. Those numbers must not be placed on the same table without an explicit disclaimer.

---

## (a) Bibliography verification table

Status codes: **OK** = authors, title, venue, year, pages, DOI/URL match a primary source; **FIX** = exists but metadata is incomplete or slightly wrong; **UPGRADE** = exists as a published paper but is filed as `@misc`.

| Key | Exists? | Authors | Title | Venue / year | Pages | DOI / arXiv / URL | Status | Description in `main.tex` |
|---|---|---|---|---|---|---|---|---|
| `wadden2020scifact` | Yes | Correct | Correct | EMNLP 2020 | 7534–7550 | 10.18653/v1/2020.emnlp-main.609; [ACL](https://aclanthology.org/2020.emnlp-main.609/) | **OK** | Accurate: claims + abstracts + rationales; SUPPORT / REFUTE / NEI. Does not mention VeriSci, the official pipeline baseline in this paper. |
| `wadden2022scifactopen` | Yes | Correct | Correct | Findings of EMNLP 2022 | 4719–4734 | 10.18653/v1/2022.findings-emnlp.347; arXiv:2210.13777 | **FIX** | Accurate: open-domain SciFact over 500K abstracts. Add `url`. |
| `niu2024ragtruth` | Yes | Correct (ACL: KaShun Shum) | Correct | ACL 2024 long | 10862–10878 | 10.18653/v1/2024.acl-long.585 | **OK** | Accurate: RAG faithfulness corpus, not a sufficiency benchmark. |
| `dhuliawala2024cove` | Yes | Correct | Correct | Findings of ACL 2024 | 3563–3578 | 10.18653/v1/2024.findings-acl.212; arXiv:2309.11495 | **OK** | Mostly accurate. CoVe isolates *verification questions from a drafted answer*. B2 isolates a *claim-blind reader over D0*. Same information-separation idea; not a reproduction. Add `url`. |
| `wei2024longform` | Yes | Correct | Correct | NeurIPS 2024 | **missing** 80756–80827 | arXiv:2403.18802; **missing** 10.52202/079017-2567 | **FIX** | Accurate: SAFE (Search-Augmented Factuality Evaluator) checks atomic facts with search. Paper writes “Safe”; official name is SAFE. |
| `ortega2025sciclaims` | Yes | **Minor:** ACL “Jose Manuel Gomez-Perez”; PDF “José Manuel Gómez-Pérez” | Correct | EMNLP 2025 System Demonstrations | 141–154 | 10.18653/v1/2025.emnlp-demos.11; **missing** arXiv:2503.18526 | **FIX** | Accurate: end-to-end Llama-3 8B pipeline (extract / retrieve / SUPPORT–REFUTE–NEI + rationale). Not a scored competitor. |
| `glockner2024missci` | Yes | Correct | Correct | ACL 2024 long | 4372–4405 | 10.18653/v1/2024.acl-long.240 | **OK** | Accurate: fallacy reconstruction over misused citations, not four-way labeling. |
| `thorne2018fever` | Yes | Correct | Correct | NAACL 2018 | 809–819 | 10.18653/v1/N18-1074 | **OK** | Accurate. |
| `aly2021feverous` | Yes | Correct | Correct | NeurIPS 2021 Datasets & Benchmarks (Round 1) | — | arXiv:2106.05707; OpenReview `h-flVCIlstW` | **FIX** | Accurate. Venue string is informal; add official booktitle + URL. |
| `manakul2023selfcheckgpt` | Yes | Correct | Correct | EMNLP 2023 | 9004–9017 | 10.18653/v1/2023.emnlp-main.557 | **OK** | Accurate as neighbouring hallucination detection. |
| `gao2023rarr` | Yes | Correct | Correct | ACL 2023 long | 16477–16508 | 10.18653/v1/2023.acl-long.910 | **OK** | Accurate: research-and-revise unsupported LM output. |
| `guo2017calibration` | Yes | Correct | Correct | ICML 2017, PMLR 70 | 1321–1330 | arXiv:1706.04599; PMLR `v70/guo17a` | **FIX** | Accurate (temperature scaling). Add PMLR URL. |
| `zhang2020trustcalibration` | Yes | Correct | Correct | FAT\* 2020 | 295–305 | 10.1145/3351095.3372852; arXiv:2001.02114 | **OK** | Accurate; paper correctly refuses a human-trust claim. |
| `zhang2024smallverifiers` | Yes | Correct | Correct | Findings of ACL 2024 | 15637–15653 | 10.18653/v1/2024.findings-acl.924; arXiv:2404.17140 | **UNUSED** | Not cited. About SLM self-correction needing strong verifiers — adjacent, not required. |
| `feng2024abstain` | Yes | Correct | Correct | ACL 2024 long | 14664–14690 | 10.18653/v1/2024.acl-long.786; arXiv:2402.00367 | **OK** | Accurate as abstention / knowledge-gap work. Add `eprint`. |
| `yue2024rafts` | Yes | Correct | Correct | ACL 2024 long | 10331–10343 | 10.18653/v1/2024.acl-long.556; arXiv:2406.09815 | **FIX** | Accurate as a retrieval-then-judge verifier. Add `url`. |
| `zheng2024rav` | Yes | Correct | Correct | Findings of ACL 2024 | 9274–9281 | 10.18653/v1/2024.findings-acl.551 | **OK** | **Overstated.** RAV is a *trained* hybrid retriever + joint FEVER verifier, not an LLM staged auditor. It argues retrieval quality dominates, which actually *supports* the paper’s negative retrieval result — but it does not “separate evidence discovery from judgment” in the LLM-agent sense. |
| `yang2022explainablefactchecking` | Yes | Correct | Correct | ICASSP 2022 | — | 10.1109/ICASSP43922.2022.9747214; arXiv:2110.05369 | **OK** | Title-accurate; thin connection (QA-style explanations, not scientific claims). |
| `vladika2024knowledge` | Yes | Correct | Correct | EACL 2024 long | 2103–2114 | 10.18653/v1/2024.eacl-long.128; **missing** arXiv:2402.02844 | **FIX** | Accurate: PubMed vs Wikipedia vs Google; BM25 precision vs dense recall. |
| `kamoi2023wice` | Yes | Correct | Correct | EMNLP 2023 | 7561–7583 | 10.18653/v1/2023.emnlp-main.470; arXiv:2303.01432 | **UNUSED** | Not cited. WiCE is real-world Wikipedia entailment; relevant to MiniCheck / LLM-AggreFact but unused. |
| `march2026` | Yes | Correct | Correct | **Now ACL 2026** (bib has `@misc` / arXiv only) | ACL long 1828 | arXiv:2603.24579; **missing** 10.18653/v1/2026.acl-long.1828 | **UPGRADE** | Accurate: Solver / Proposer / Checker with Checker blinded to the Solver output. |
| `hirsch2026blame` | Yes | Correct | Correct | **Now EMNLP 2026** (bib has `@misc`) | 38261–38286 | arXiv:2608.24306; [ACL](https://aclanthology.org/2026.emnlp-main.1681/) | **UPGRADE** | Accurate: trace-level citation/faithfulness errors, not end-user verdicts. |
| `yu2026rt4chart` | Yes | Correct (Muñoz) | Correct | arXiv 2026-03-29 (no venue found) | — | arXiv:2603.27752 | **OK** as preprint | **Loose.** RT4CHART is a RAG hallucination detector (entailed / contradicted / baseless) with local-then-global verification. Calling it “a systematic auditor for RAG” is promotional. |
| `yang2026calibratedselective` | Yes | Correct (Dekun Yang, sole author) | Correct | arXiv 2026 (no venue found) | — | arXiv:2607.18240 | **OK** as preprint | Directionally accurate (selective fact-checking + abstention). Over-cites a 95-claim preprint as if it “formalises” the risk–coverage trade-off; that formalisation is El-Yaniv & Wiener (2010). |
| `march2026code` | Yes | Org `{Qwen-Applications}` is fine | Fine | GitHub, created 2026-03-25 | — | https://github.com/Qwen-Applications/MARCH | **OK** | Accurate. |
| `scifactdata` | Yes | `{Allen Institute for AI}` is fine | Fine | GitHub | — | https://github.com/allenai/scifact | **UNUSED** | Not cited. The paper cites `wadden2020scifact` for the dataset, which is enough. |

### Unused keys (in `references.bib`, never cited in `main.tex`)

- `zhang2024smallverifiers`
- `kamoi2023wice`
- `scifactdata`

### Missing keys (cited in `main.tex` but absent from the bib)

None.

### Description-accuracy notes (cited works)

| Citation | Verdict | Note |
|---|---|---|
| CoVe as “closest published analogue” to B2 | Acceptable with a hedge | CoVe self-checks a generated answer via isolated verification QA. B2 claim-blinds a reader over the *original citations*. Same isolation idea; different task. |
| SAFE as the “reference point for our fresh retrieval arm” | Acceptable | SAFE is an *evaluator of long-form generation*, not a scientific-claim verifier. |
| MARCH as “information separation between proposer and checker” | Accurate | Checker is blinded to the Solver response. |
| Hirsch as “reason not to claim” trace-level attribution | Accurate | |
| Yu / RT4CHART as “systematic auditor” | Too strong | Hallucination detector, three labels, RAGTruth-family eval. |
| RAFTS + RAV as “retrieval-augmented verifiers” that “motivate separating evidence discovery from judgment” | Half-right | RAFTS yes. RAV is a trained FEVER pipeline whose thesis is “retrieval is almost all you need,” which is closer to the paper’s *negative* retrieval finding. |
| Yang 2026 ECE as the formalisation of the precision–coverage trade-off | Too strong | Cite El-Yaniv & Wiener / Geifman & El-Yaniv for the formalism; keep Yang 2026 as a concurrent fact-checking application. |

---

## (b) Ready-to-paste BibTeX

### Corrected existing entries

```bibtex
@inproceedings{wadden2022scifactopen,
  title     = {{SciFact-Open}: Towards open-domain scientific claim verification},
  author    = {Wadden, David and Lo, Kyle and Kuehl, Bailey and Cohan, Arman and Beltagy, Iz and Wang, Lucy Lu and Hajishirzi, Hannaneh},
  booktitle = {Findings of the Association for Computational Linguistics: EMNLP 2022},
  pages     = {4719--4734},
  year      = {2022},
  doi       = {10.18653/v1/2022.findings-emnlp.347},
  url       = {https://aclanthology.org/2022.findings-emnlp.347/},
  eprint    = {2210.13777},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL}
}

@inproceedings{wei2024longform,
  title     = {Long-form factuality in large language models},
  author    = {Wei, Jerry and Yang, Chengrun and Song, Xinying and Lu, Yifeng and Hu, Nathan and Huang, Jie and Tran, Dustin and Peng, Daiyi and Liu, Ruibo and Huang, Da and Du, Cosmo and Le, Quoc V.},
  booktitle = {Advances in Neural Information Processing Systems},
  volume    = {37},
  pages     = {80756--80827},
  year      = {2024},
  doi       = {10.52202/079017-2567},
  eprint    = {2403.18802},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL}
}

@inproceedings{ortega2025sciclaims,
  title     = {{SciClaims}: An End-to-End Generative System for Biomedical Claim Analysis},
  author    = {Ortega, Ra{\'u}l and G{\'o}mez-P{\'e}rez, Jos{\'e} Manuel},
  booktitle = {Proceedings of the 2025 Conference on Empirical Methods in Natural Language Processing: System Demonstrations},
  pages     = {141--154},
  year      = {2025},
  doi       = {10.18653/v1/2025.emnlp-demos.11},
  url       = {https://aclanthology.org/2025.emnlp-demos.11/},
  eprint    = {2503.18526},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL}
}

@inproceedings{aly2021feverous,
  title     = {{FEVEROUS}: Fact Extraction and {VER}ification Over Unstructured and Structured Information},
  author    = {Aly, Rami and Guo, Zhijiang and Schlichtkrull, Michael and Thorne, James and Vlachos, Andreas and Christodoulopoulos, Christos and Cocarascu, Oana and Mittal, Arpit},
  booktitle = {Proceedings of the Neural Information Processing Systems Track on Datasets and Benchmarks},
  year      = {2021},
  url       = {https://openreview.net/forum?id=h-flVCIlstW},
  eprint    = {2106.05707},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL}
}

@inproceedings{guo2017calibration,
  title     = {On Calibration of Modern Neural Networks},
  author    = {Guo, Chuan and Pleiss, Geoff and Sun, Yu and Weinberger, Kilian Q.},
  booktitle = {Proceedings of the 34th International Conference on Machine Learning},
  series    = {Proceedings of Machine Learning Research},
  volume    = {70},
  pages     = {1321--1330},
  year      = {2017},
  url       = {https://proceedings.mlr.press/v70/guo17a.html},
  eprint    = {1706.04599},
  archivePrefix = {arXiv}
}

@inproceedings{yue2024rafts,
  title     = {Retrieval Augmented Fact Verification by Synthesizing Contrastive Arguments},
  author    = {Yue, Zhenrui and Zeng, Huimin and Shang, Lanyu and Liu, Yifan and Zhang, Yang and Wang, Dong},
  booktitle = {Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)},
  pages     = {10331--10343},
  year      = {2024},
  doi       = {10.18653/v1/2024.acl-long.556},
  url       = {https://aclanthology.org/2024.acl-long.556/},
  eprint    = {2406.09815},
  archivePrefix = {arXiv}
}

@inproceedings{vladika2024knowledge,
  title     = {Comparing Knowledge Sources for Open-Domain Scientific Claim Verification},
  author    = {Vladika, Juraj and Matthes, Florian},
  booktitle = {Proceedings of the 18th Conference of the European Chapter of the Association for Computational Linguistics (Volume 1: Long Papers)},
  pages     = {2103--2114},
  year      = {2024},
  doi       = {10.18653/v1/2024.eacl-long.128},
  url       = {https://aclanthology.org/2024.eacl-long.128/},
  eprint    = {2402.02844},
  archivePrefix = {arXiv}
}

@inproceedings{dhuliawala2024cove,
  title     = {Chain-of-Verification Reduces Hallucination in Large Language Models},
  author    = {Dhuliawala, Shehzaad and Komeili, Mojtaba and Xu, Jing and Raileanu, Roberta and Li, Xian and Celikyilmaz, Asli and Weston, Jason},
  booktitle = {Findings of the Association for Computational Linguistics: ACL 2024},
  pages     = {3563--3578},
  year      = {2024},
  doi       = {10.18653/v1/2024.findings-acl.212},
  url       = {https://aclanthology.org/2024.findings-acl.212/},
  eprint    = {2309.11495},
  archivePrefix = {arXiv}
}

@inproceedings{march2026,
  title     = {{MARCH}: Multi-Agent Reinforced Self-Check for {LLM} Hallucination},
  author    = {Li, Zhuo and Zhang, Yupeng and Cheng, Pengyu and Song, Jiajun and Zhou, Mengyu and Li, Hao and Hu, Shujie and Qin, Yu and Zhao, Erchao and Jiang, Xiaoxi and Jiang, Guanjun},
  booktitle = {Proceedings of the 64th Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)},
  year      = {2026},
  doi       = {10.18653/v1/2026.acl-long.1828},
  eprint    = {2603.24579},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL}
}

@inproceedings{hirsch2026blame,
  title     = {Who is the Agent to Blame? Localizing Faithfulness and Citation Mistakes in Agentic Deep Research},
  author    = {Hirsch, Eran and Wan, David and Wang, Han and Stengel-Eskin, Elias and Bansal, Mohit and Dagan, Ido},
  booktitle = {Proceedings of the 2026 Conference on Empirical Methods in Natural Language Processing},
  pages     = {38261--38286},
  year      = {2026},
  url       = {https://aclanthology.org/2026.emnlp-main.1681/},
  eprint    = {2608.24306},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL}
}
```

Leave `yu2026rt4chart` and `yang2026calibratedselective` as `@misc` (no published venue found as of 2026-10-27). Add `doi = {10.48550/arXiv.2603.27752}` and `doi = {10.48550/arXiv.2607.18240}` if desired.

### New entries a reviewer would demand

Only works verified to exist are included.

```bibtex
% --- SciFact baselines / SOTA ---
@inproceedings{wadden2022multivers,
  title     = {{MultiVerS}: Improving scientific claim verification with weak supervision and full-document context},
  author    = {Wadden, David and Lo, Kyle and Wang, Lucy Lu and Cohan, Arman and Beltagy, Iz and Hajishirzi, Hannaneh},
  booktitle = {Findings of the Association for Computational Linguistics: NAACL 2022},
  pages     = {61--76},
  year      = {2022},
  doi       = {10.18653/v1/2022.findings-naacl.6},
  url       = {https://aclanthology.org/2022.findings-naacl.6/},
  eprint    = {2112.01640},
  archivePrefix = {arXiv}
}

@inproceedings{li2021paragraphjoint,
  title     = {A Paragraph-level Multi-task Learning Model for Scientific Fact-Verification},
  author    = {Li, Xiangci and Burns, Gully and Peng, Nanyun},
  booktitle = {Proceedings of the Workshop on Scientific Document Understanding co-located with AAAI 2021},
  series    = {CEUR Workshop Proceedings},
  volume    = {2831},
  year      = {2021},
  url       = {https://ceur-ws.org/Vol-2831/paper8.pdf},
  eprint    = {2012.14500},
  archivePrefix = {arXiv}
}

@inproceedings{zhang2021arsjoint,
  title     = {Abstract, Rationale, Stance: A Joint Model for Scientific Claim Verification},
  author    = {Zhang, Zhiwei and Li, Jiyi and Fukumoto, Fumiyo and Ye, Yanming},
  booktitle = {Proceedings of the 2021 Conference on Empirical Methods in Natural Language Processing},
  pages     = {3580--3586},
  year      = {2021},
  doi       = {10.18653/v1/2021.emnlp-main.290},
  url       = {https://aclanthology.org/2021.emnlp-main.290/},
  eprint    = {2110.15116},
  archivePrefix = {arXiv}
}

% VeriSci is the pipeline baseline of wadden2020scifact; cite that paper, not a separate key.

% --- Neighbouring scientific / biomedical claim datasets ---
@inproceedings{sarrouti2021healthver,
  title     = {Evidence-based Fact-Checking of Health-related Claims},
  author    = {Sarrouti, Mourad and Ben Abacha, Asma and Mrabet, Yassine and Demner-Fushman, Dina},
  booktitle = {Findings of the Association for Computational Linguistics: EMNLP 2021},
  pages     = {3499--3512},
  year      = {2021},
  doi       = {10.18653/v1/2021.findings-emnlp.297},
  url       = {https://aclanthology.org/2021.findings-emnlp.297/}
}

@inproceedings{saakyan2021covidfact,
  title     = {{COVID}-Fact: Fact Extraction and Verification of Real-World Claims on {COVID}-19 Pandemic},
  author    = {Saakyan, Arkadiy and Chakrabarty, Tuhin and Muresan, Smaranda},
  booktitle = {Proceedings of the 59th Annual Meeting of the Association for Computational Linguistics and the 11th International Joint Conference on Natural Language Processing (Volume 1: Long Papers)},
  pages     = {2116--2129},
  year      = {2021},
  doi       = {10.18653/v1/2021.acl-long.165},
  url       = {https://aclanthology.org/2021.acl-long.165/},
  eprint    = {2106.03794},
  archivePrefix = {arXiv}
}

@inproceedings{wang2023checkcovid,
  title     = {Check-{COVID}: Fact-Checking {COVID}-19 News Claims with Scientific Evidence},
  author    = {Wang, Gengyu and Harwood, Kate and Chillrud, Lawrence and Ananthram, Amith and Subbiah, Melanie and McKeown, Kathleen},
  booktitle = {Findings of the Association for Computational Linguistics: ACL 2023},
  pages     = {14114--14127},
  year      = {2023},
  doi       = {10.18653/v1/2023.findings-acl.888},
  url       = {https://aclanthology.org/2023.findings-acl.888/},
  eprint    = {2305.18265},
  archivePrefix = {arXiv}
}

@inproceedings{schlichtkrull2023averitec,
  title     = {{AVeriTeC}: A Dataset for Real-world Claim Verification with Evidence from the Web},
  author    = {Schlichtkrull, Michael Sejr and Guo, Zhijiang and Vlachos, Andreas},
  booktitle = {Advances in Neural Information Processing Systems Datasets and Benchmarks Track},
  year      = {2023},
  url       = {https://openreview.net/forum?id=fKzSz0oyaI},
  eprint    = {2305.13117},
  archivePrefix = {arXiv}
}

% --- LLM fact-checking / atomic evaluation ---
@inproceedings{min2023factscore,
  title     = {{FActScore}: Fine-grained Atomic Evaluation of Factual Precision in Long Form Text Generation},
  author    = {Min, Sewon and Krishna, Kalpesh and Lyu, Xinxi and Lewis, Mike and Yih, Wen-tau and Koh, Pang Wei and Iyyer, Mohit and Zettlemoyer, Luke and Hajishirzi, Hannaneh},
  booktitle = {Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing},
  pages     = {12076--12100},
  year      = {2023},
  doi       = {10.18653/v1/2023.emnlp-main.741},
  url       = {https://aclanthology.org/2023.emnlp-main.741/},
  eprint    = {2305.14251},
  archivePrefix = {arXiv}
}

@inproceedings{tang2024minicheck,
  title     = {{MiniCheck}: Efficient Fact-Checking of {LLMs} on Grounding Documents},
  author    = {Tang, Liyan and Laban, Philippe and Durrett, Greg},
  booktitle = {Proceedings of the 2024 Conference on Empirical Methods in Natural Language Processing},
  pages     = {8818--8847},
  year      = {2024},
  doi       = {10.18653/v1/2024.emnlp-main.499},
  url       = {https://aclanthology.org/2024.emnlp-main.499/},
  eprint    = {2404.10774},
  archivePrefix = {arXiv}
}

@inproceedings{zheng2023llmasjudge,
  title     = {Judging {LLM}-as-a-Judge with {MT}-Bench and Chatbot Arena},
  author    = {Zheng, Lianmin and Chiang, Wei-Lin and Sheng, Ying and Zhuang, Siyuan and Wu, Zhanghao and Zhuang, Yonghao and Lin, Zi and Li, Zhuohan and Li, Dacheng and Xing, Eric P. and Zhang, Hao and Gonzalez, Joseph E. and Stoica, Ion},
  booktitle = {Advances in Neural Information Processing Systems},
  volume    = {36},
  year      = {2023},
  eprint    = {2306.05685},
  archivePrefix = {arXiv}
}

% --- Selective prediction / conformal abstention ---
@article{elyaniv2010selective,
  title   = {On the Foundations of Noise-free Selective Classification},
  author  = {El-Yaniv, Ran and Wiener, Yair},
  journal = {Journal of Machine Learning Research},
  volume  = {11},
  number  = {53},
  pages   = {1605--1641},
  year    = {2010},
  url     = {https://jmlr.org/papers/v11/el-yaniv10a.html}
}

@inproceedings{geifman2017selective,
  title     = {Selective Classification for Deep Neural Networks},
  author    = {Geifman, Yonatan and El-Yaniv, Ran},
  booktitle = {Advances in Neural Information Processing Systems},
  volume    = {30},
  year      = {2017},
  eprint    = {1705.08500},
  archivePrefix = {arXiv}
}

@inproceedings{mohri2024conformal,
  title     = {Language Models with Conformal Factuality Guarantees},
  author    = {Mohri, Christopher and Hashimoto, Tatsunori},
  booktitle = {Proceedings of the 41st International Conference on Machine Learning},
  series    = {Proceedings of Machine Learning Research},
  volume    = {235},
  pages     = {36029--36047},
  year      = {2024},
  url       = {https://proceedings.mlr.press/v235/mohri24a.html},
  eprint    = {2402.10978},
  archivePrefix = {arXiv}
}

% --- Knowledge conflicts ---
@inproceedings{xie2024chameleon,
  title     = {Adaptive Chameleon or Stubborn Sloth: Revealing the Behavior of Large Language Models in Knowledge Conflicts},
  author    = {Xie, Jian and Zhang, Kai and Chen, Jiangjie and Lou, Renze and Su, Yu},
  booktitle = {The Twelfth International Conference on Learning Representations},
  year      = {2024},
  url       = {https://openreview.net/forum?id=auKAUJZMO6},
  eprint    = {2305.13300},
  archivePrefix = {arXiv}
}

@inproceedings{wu2024clasheval,
  title     = {{ClashEval}: Quantifying the tug-of-war between an {LLM}'s internal prior and external evidence},
  author    = {Wu, Kevin and Wu, Eric and Zou, James},
  booktitle = {Advances in Neural Information Processing Systems Datasets and Benchmarks Track},
  pages     = {33402--33422},
  year      = {2024},
  doi       = {10.52202/079017-1053},
  eprint    = {2404.10198},
  archivePrefix = {arXiv}
}

% --- Citation / attribution evaluation ---
@inproceedings{gao2023alce,
  title     = {Enabling Large Language Models to Generate Text with Citations},
  author    = {Gao, Tianyu and Yen, Howard and Yu, Jiatong and Chen, Danqi},
  booktitle = {Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing},
  pages     = {6465--6488},
  year      = {2023},
  doi       = {10.18653/v1/2023.emnlp-main.398},
  url       = {https://aclanthology.org/2023.emnlp-main.398/},
  eprint    = {2305.14627},
  archivePrefix = {arXiv}
}

@inproceedings{li2024attributionbench,
  title     = {{AttributionBench}: How Hard is Automatic Attribution Evaluation?},
  author    = {Li, Yifei and Yue, Xiang and Liao, Zeyi and Sun, Huan},
  booktitle = {Findings of the Association for Computational Linguistics: ACL 2024},
  pages     = {14919--14935},
  year      = {2024},
  doi       = {10.18653/v1/2024.findings-acl.886},
  url       = {https://aclanthology.org/2024.findings-acl.886/},
  eprint    = {2402.15089},
  archivePrefix = {arXiv}
}

% --- Benchmark contamination ---
@inproceedings{magar2022contamination,
  title     = {Data Contamination: From Memorization to Exploitation},
  author    = {Magar, Inbal and Schwartz, Roy},
  booktitle = {Proceedings of the 60th Annual Meeting of the Association for Computational Linguistics (Volume 2: Short Papers)},
  pages     = {157--165},
  year      = {2022},
  doi       = {10.18653/v1/2022.acl-short.18},
  url       = {https://aclanthology.org/2022.acl-short.18/},
  eprint    = {2203.08242},
  archivePrefix = {arXiv}
}

@inproceedings{jacovi2023contamination,
  title     = {Stop Uploading Test Data in Plain Text: Practical Strategies for Mitigating Data Contamination by Evaluation Benchmarks},
  author    = {Jacovi, Alon and Caciularu, Avi and Goldman, Omer and Goldberg, Yoav},
  booktitle = {Proceedings of the 2023 Conference on Empirical Methods in Natural Language Processing},
  pages     = {5075--5084},
  year      = {2023},
  doi       = {10.18653/v1/2023.emnlp-main.308},
  url       = {https://aclanthology.org/2023.emnlp-main.308/}
}

% --- Recent scientific claim verification with LLMs (verified 2024--2026) ---
@inproceedings{alvarez2024zeroshot,
  title     = {Zero-shot Scientific Claim Verification Using {LLMs} and Citation Text},
  author    = {Alvarez, Carlos and Bennett, Maxwell and Wang, Lucy Lu},
  booktitle = {Proceedings of the Fourth Workshop on Scholarly Document Processing ({SDP} 2024)},
  pages     = {269--276},
  year      = {2024},
  url       = {https://aclanthology.org/2024.sdp-1.25/}
}

@inproceedings{gonzalez2025triplecheck,
  title     = {{TripleCheck}: Transparent Post-Hoc Verification of Biomedical Claims in {AI}-Generated Answers},
  author    = {Gonz{\'a}lez, Ana Valeria and Boldsen, Sidsel and Hangelbroek, Roland},
  booktitle = {Proceedings of the Fourth Workshop on Bridging Human-Computer Interaction and Natural Language Processing ({HCI}+{NLP})},
  pages     = {33--47},
  year      = {2025},
  doi       = {10.18653/v1/2025.hcinlp-1.4},
  url       = {https://aclanthology.org/2025.hcinlp-1.4/}
}

@inproceedings{wang2025sciver,
  title     = {{SciVer}: Evaluating Foundation Models for Multimodal Scientific Claim Verification},
  author    = {Wang, Chengye and Shen, Yifei and Kuang, Zexi and Cohan, Arman and Zhao, Yilun},
  booktitle = {Proceedings of the 63rd Annual Meeting of the Association for Computational Linguistics (Volume 1: Long Papers)},
  pages     = {8562--8579},
  year      = {2025},
  doi       = {10.18653/v1/2025.acl-long.420},
  url       = {https://aclanthology.org/2025.acl-long.420/}
}

@misc{rao2026thinkncheck,
  title        = {{ThinknCheck}: Grounded Claim Verification with Compact, Reasoning-Driven, and Interpretable Models},
  author       = {Rao, Delip and Han, Feijiang and Callison-Burch, Chris},
  year         = {2026},
  eprint       = {2604.01652},
  archivePrefix = {arXiv},
  primaryClass = {cs.CL}
}
```

---

## (c) Suggested sentences by related-work subsection

### Verification datasets and scientific claim checking

Insert after the SciFact / SciFact-Open sentences, before Missci:

> Official SciFact systems are retrieval-plus-rationale pipelines, not claim-level classifiers. VeriSci \citep{wadden2020scifact} is the original sentence-level cascade (TF-IDF abstract retrieval, then BERT rationale selection, then stance). ParagraphJoint \citep{li2021paragraphjoint} jointly trains rationale selection and stance over a compact paragraph encoding, and ARSJoint \citep{zhang2021arsjoint} adds abstract retrieval to that joint objective. MultiVerS \citep{wadden2022multivers} is the usual supervised reference point: a Longformer that predicts an abstract-level SUPPORT/REFUTE label and sentence rationales together, reporting about 72.5 abstract-level label-only F1 and 67.2 sentence-level Selection+Label F1 on SciFact. Those numbers are not interchangeable with the claim-level three-way micro-F1 we report.

Insert after Vladika / SciClaims, as neighbouring biomedical datasets:

> Closely related biomedical sets that a scientific-claim paper is expected to locate: HealthVer \citep{sarrouti2021healthver} pairs real COVID search-engine claims with scientific evidence (SUPPORT/REFUTE/NEUTRAL); COVID-Fact \citep{saakyan2021covidfact} is a FEVER-style COVID set with automatically generated counter-claims; and Check-COVID \citep{wang2023checkcovid} checks news claims against CORD-19 scientific evidence. AVeriTeC \citep{schlichtkrull2023averitec} is the current open-web fact-checking standard and already uses a four-way label set (Supported / Refuted / Not Enough Evidence / Conflicting Evidence), which is the closest published analogue to our unaddressed vs.\ underdetermined split.

Insert as a 2024–2026 LLM-on-SciFact paragraph:

> LLM-only scientific verification is no longer empty. Alvarez et al.\ \citep{alvarez2024zeroshot} show that GPT-4 few-shot prompting on citance–abstract pairs matches MultiVerS within about one official-metric F1 point on SciFact. TripleCheck \citep{gonzalez2025triplecheck} reports 0.70 claim-level F1 on the SciFact development set in a zero-shot setting by checking extracted triples against retrieved context and a biomedical KG. ThinknCheck \citep{rao2026thinkncheck} is a 1B reasoning verifier that reports 64.7 balanced accuracy on SciFact development, above MiniCheck-7B. SciVer \citep{wang2025sciver} moves the task into multimodal scientific papers. We do not reproduce these systems; we cite them so that our prompt-level B2/V comparison is not mistaken for the only LLM result on SciFact.

### LLM verifiers, self-checking agents, and retrieval

Insert after CoVe / SAFE, before MARCH:

> The primitive our judge implements — “is this statement supported by these documents?” — is now a standard LLM-as-a-judge operation \citep{zheng2023llmasjudge}. FActScore \citep{min2023factscore} decomposes long-form text into atomic facts and scores the fraction supported by a knowledge source; SAFE \citep{wei2024longform} is the search-augmented successor. MiniCheck \citep{tang2024minicheck} shows that a 770M model trained on synthetic hard negatives can match GPT-4 on document-grounded fact-checking at far lower cost. Those systems check *generated text against grounding documents*. We check *an already-atomic scientific claim against retrieved abstracts*, so we inherit their isolation idea and not their metric.

Insert after the citation-auditor / Hirsch sentence:

> Citation adequacy is its own evaluation problem. ALCE \citep{gao2023alce} measures whether a cited passage actually supports the generated sentence; AttributionBench \citep{li2024attributionbench} shows that even fine-tuned GPT-3.5 reaches only about 80% macro-F1 on binary attribution. Our auditor rates each D0 citation as adequate / inadequate / unverifiable; we do not claim an ALCE-style citation-precision number.

Insert after the D0/D1 disagreement discussion (or in this subsection’s last paragraph):

> When two evidence scopes disagree, the model is in a knowledge-conflict regime. Xie et al.\ \citep{xie2024chameleon} show that LLMs will follow coherent external evidence but revert to their parametric prior when some of the context agrees with that prior. ClashEval \citep{wu2024clasheval} quantifies the same tug-of-war and finds models override a correct prior more than 60% of the time given incorrect retrieved content. Our reconciler’s default to underdetermined is a conservative policy in that literature, not a new theory of conflict.

### Abstention, calibration, and selective use

Replace or precede the current opening (“Work on abstention \citep{feng2024abstain} and on calibrated selective fact checking \citep{yang2026calibratedselective} formalises the trade-off we measure”):

> The precision–coverage curve we plot is the risk–coverage trade-off of selective classification \citep{elyaniv2010selective,geifman2017selective}: a reject option that trades coverage for lower error among accepted claims. Feng et al.\ \citep{feng2024abstain} study when an LLM should abstain because of a knowledge gap; Yang \citep{yang2026calibratedselective} is a concurrent fact-checking application that emits an uncertain verdict. Neither paper is the formalism. Conformal methods give the missing guarantee: Mohri and Hashimoto \citep{mohri2024conformal} back off generation until a target factuality level holds with high probability. We do not conformalize; we accept a claim only when D0 and D1 agree, and we report error among accepted claims as a function of coverage.

Insert as a short contamination caveat (limitations or this subsection):

> SciFact has been public since 2020 and is a plausible pretraining contaminant \citep{magar2022contamination,jacovi2023contamination}. Condition B0 (claim only, no evidence) is our only check on parametric leakage; we do not run a canary or membership test, so any absolute accuracy number — especially under B0 — should be read as an upper bound on what a frozen 2020 benchmark can tell us about unseen scientific claims.

---

## SciFact metric positioning (reviewer note)

The paper scores **one three-way label per claim** (SUPPORT / REFUTE / NEI), then reports per-class P/R/F1, micro-F1, macro-F1, and false endorsement.

Official SciFact \citep{wadden2020scifact,wadden2022multivers} scores a **retrieval-plus-rationale pipeline**:

| Official metric | What it requires |
|---|---|
| Abstract-level Label-Only F1 | Correct SUPPORT/REFUTE on the right abstracts (NEI abstracts are not in the positive set) |
| Abstract-level Label+Rationale F1 | Same, plus the predicted rationale set covers a gold rationale |
| Sentence-level Selection-Only F1 | Exact rationale-sentence identification |
| Sentence-level Selection+Label F1 | Rationale sentences *and* the abstract label |

Published reference points (do **not** put these in the same column as this paper’s micro-F1):

- VeriSci (Wadden et al., 2020), SciFact development, BioBERT/RoBERTa pipeline: roughly 52 abstract-level F1 / 48 sentence-level F1 in later reproductions \citep{zhang2021arsjoint}.
- ParagraphJoint (Li et al., 2021), SciFact test: 67.2 abstract-level Label+Rationale F1, 60.9 sentence-level Selection+Label F1.
- ARSJoint (Zhang et al., 2021), SciFact development, BioBERT: 66.7 abstract-level F1, 66.2 sentence-level F1.
- MultiVerS (Wadden et al., 2022), fully supervised SciFact: **72.5** abstract-level label-only F1, **67.2** sentence-level Selection+Label F1. This is the number reviewers will look for.
- Alvarez et al. (2024): GPT-4 few-shot is within ~1 official-metric F1 of MultiVerS on the SciFact test set.
- TripleCheck (González et al., 2025): 0.70 F1 on SciFact *development*, after mapping triples back to a claim-level label — the only published number that is methodologically close to this paper, and it should be cited as such.

**How to write the comparison in the paper:**

1. State once, in Metrics and again in Related Work, that the scored unit is a *claim-level three-way label*, not an abstract-level or sentence-level SciFact decision.
2. State that official test labels are unused (already done) and that the public development split is the local held-out set (already done).
3. If a table needs a “prior SciFact number,” report MultiVerS abstract-level label-only F1 as *supervised pipeline SOTA under the official protocol*, and Alvarez et al.\ as *the closest LLM result under that same official protocol*. Put this paper’s micro-F1 in a separate block labelled “claim-level 3-way (this work).”
4. False endorsement has no official SciFact counterpart. The closest published ideas are FActScore precision (fraction of atomic facts supported) and selective-prediction error-at-coverage. Keep FE as a first-class metric; do not rename it “SciFact precision.”
5. Because SciFact gold documents are a subset of the cited documents, independent retrieval cannot find *new gold evidence* on this corpus. That bound (already in the retrieval table) is the reason a reviewer should not demand a SciFact-Open comparison unless the authors actually run one.

---

## Priority order if the related-work page budget is tight

1. MultiVerS + one sentence on VeriSci / ParagraphJoint / ARSJoint (metric positioning).
2. El-Yaniv & Wiener + Geifman & El-Yaniv (the actual selective-prediction formalism).
3. Alvarez 2024 and TripleCheck 2025 (LLM-on-SciFact, so the negative result has neighbours).
4. MiniCheck + FActScore (the LLM fact-checking primitive).
5. Xie 2024 / ClashEval (D0–D1 conflict).
6. ALCE (citation auditor).
7. HealthVer / Check-COVID / AVeriTeC (dataset neighbourhood).
8. Jacovi 2023 (contamination caveat on B0).

Everything else in section (b) is useful but secondary.
