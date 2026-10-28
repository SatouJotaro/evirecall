# References and selection notes

Primary sources supporting proposal v0.3, 27 October 2026. Bibliographic metadata: [BibTeX](references.bib). Local source snapshots live in `project/library/`, outside this repository; their manifest records full commits and PDF hashes. Inclusion here does not make a resource a required experiment.

<a id="smurfs"></a>
## 1. Smurfs: Multi-Agent System using Context-Efficient DFSDT for Tool Planning

Selected backbone. Read inference/smurfs_worker.py and the planner/executor/answer/verifier roles. The memory_agent.py placeholder is empty in the pinned snapshot; persistent memory is proposed work.

[Paper](https://aclanthology.org/2025.naacl-long.169.pdf) · [Repository](https://github.com/FreedomIntelligence/Smurfs). Source snapshot: `0f5c44701f6c9e5ac9caed9edc4ce16ad9c430c3`.

<a id="tiermem"></a>
## 2. From Lossy to Verified: A Provenance-Aware Tiered Memory for Agents

Read the paper and jev_tiermem/system.py separately. The trained paper router and lightweight Jev implementation are not the same baseline. The downloaded preprint is verified; the separate OpenReview PDF returned HTTP 403.

[Paper](https://arxiv.org/pdf/2602.17913) · [Repository](https://github.com/FreedomIntelligence/Tiermem). Source snapshot: `d0d3896e917117ba0fcc1501e2b2dae891d2a2e3`.

<a id="jev"></a>
## 3. Jev TierMem (software)

Lightweight software in the TierMem repository, distinct from the trained-router paper implementation. Relevant operations: observe, add_summary, retrieve, promote. Real service access and end-to-end integration remain pilot checks.

[Pinned source](https://github.com/FreedomIntelligence/Tiermem/tree/d0d3896e917117ba0fcc1501e2b2dae891d2a2e3/jev_tiermem).

<a id="longmemeval"></a>
## 4. LongMemEval: Benchmarking Chat Assistants on Long-Term Interactive Memory

Primary general-memory evaluation: 500 questions. Use the cleaned release; S/M/oracle are context variants, not train/dev/test. Strip answer and evidence-location labels before ingestion.

[Paper](https://arxiv.org/pdf/2410.10813) · [Repository](https://github.com/xiaowu0162/LongMemEval). Source snapshot: `9e0b455f4ef0e2ab8f2e582289761153549043fc`.

<a id="memoryarena"></a>
## 5. MemoryArena: Benchmarking Agent Memory in Interdependent Multi-Session Agentic Tasks

Candidate action environment. Read setup_travel.md: 270 groups, local CSV tools, separately hosted flight database. Repository labels itself preview. Pilot before promising integration; prevent ground-truth feedback from reaching the agent.

[Paper](https://arxiv.org/pdf/2602.16313) · [Repository](https://github.com/ZexueHe/MemoryArena). Source snapshot: `6cd9de14b71915e39ac742a20dc33785e14b6aab`.

<a id="mast"></a>
## 6. Why Do Multi-Agent LLM Systems Fail?

Failure-analysis reference: downloaded paper v3 describes 1,600+ annotated traces, 7 frameworks, and 14 failure modes. The older README links MAD; use the paper-linked MAST-Data release/version explicitly. Not an executable memory-training benchmark.

[Paper](https://arxiv.org/pdf/2503.13657) · [Repository](https://github.com/multi-agent-systems-failure-taxonomy/MAST). Source snapshot: `a70542e541b2104ef8fcd785778179e173fb8d70`.

<a id="governed"></a>
## 7. Governed Shared Memory for Multi-Agent LLM Systems

Related shared-state architecture. The current Caura (formerly MemClaw) repository is available; it is not the exact paper-version service. The separate paper-linked ArgusFleet harness is unavailable at the supplied URL. Do not claim full paper reproduction from Caura alone.

[Paper](https://arxiv.org/pdf/2606.24535) · [Repository](https://github.com/caura-ai/caura). Source snapshot: `6904eef15f06817573b616b33640aadc5638d8c3`.

<a id="deepagents"></a>
## 8. Deep Agents

Engineering alternative. Read the official repository documentation for subagents, context handling, and memory. No separate research paper is assigned here; built-in features are upstream contributions.

[Repository](https://github.com/langchain-ai/deepagents). Source snapshot: `3413029245643eb9915b506def3e4817af548f0e`.

<a id="memoryagentbench"></a>
## 9. Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions

Fallback and broader memory reference. Covers retrieval, test-time learning, long-range understanding, and selective forgetting. Some sources overlap LongMemEval; it is not automatically an independent second test set.

[Paper](https://arxiv.org/pdf/2507.05257) · [Repository](https://github.com/HUST-AI-HYZ/MemoryAgentBench). Source snapshot: `538026089d1a8a8eff05121d0db89b388f360eba`.

<a id="stale"></a>
## 10. STALE: Can LLM Agents Know When Their Memories Are No Longer Valid?

Primary stale-memory evaluation: 400 scenarios and 1,200 queries. Includes CUP-Mem, a close baseline for write-time state revision. Official dataset exists on Hugging Face; generation scripts alone are not the released benchmark. Distractors reuse LongMemEval material.

[Paper](https://arxiv.org/pdf/2605.06527) · [Repository](https://github.com/icedreamc/STALE). Source snapshot: `ea7d391103a151927cd29d2f01d87597a782bdcb`.

<a id="magentic"></a>
## 11. Magentic-One: A Generalist Multi-Agent System for Solving Complex Tasks

Paper plus Microsoft AutoGen source. Current implementation is under python/packages/autogen-ext/src/autogen_ext/teams/magentic_one; the earlier autogen-magentic-one package is deprecated. Current AutoGen README announces archival; this is an architectural reference, not the selected backbone.

[Paper](https://arxiv.org/pdf/2411.04468) · [Repository](https://github.com/microsoft/autogen). Source snapshot: `004749e6b7102c8fd317b9b1499ce5807223c278`.

<a id="twinmarket"></a>
## 12. TwinMarket: A Scalable Behavioral and Social Simulation for Financial Markets

Teacher-team finance/social-simulation reference. Requires a different domain and evaluation design; not a required implementation target.

[Paper](https://arxiv.org/pdf/2502.01506) · [Repository](https://github.com/FreedomIntelligence/TwinMarket). Source snapshot: `de5f2446fcba0d0aba533a6adaede034160e29b4`.

<a id="easymed"></a>
## 13. Human or LLM as Standardized Patients? A Comparative Study in Medical Education

Teacher-team medical-education reference. Local PDF title uses 'in Medical Education'; repository citation uses 'for Medical Education'. Same arXiv identifier; preserve the title/version distinction.

[Paper](https://arxiv.org/pdf/2511.14783) · [Repository](https://github.com/FreedomIntelligence/EasyMED). Source snapshot: `c1c32a4ddb6671f069d77d1a4caf454c42c3c741`.

<a id="amem"></a>
## 14. A-MEM: Agentic Memory for LLM Agents

Additional memory-method reading: dynamic notes, links, and memory evolution. Runtime repository and paper evaluation repository are separate.

[Paper](https://arxiv.org/pdf/2502.12110) · [Repository](https://github.com/agiresearch/A-mem). Source snapshot: `ceffb860f0712bbae97b184d440df62bc910ca8d`.

<a id="mem0"></a>
## 15. Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory

Additional engineering and memory-update reference. Current software has evolved since the paper; version-pin comparisons instead of inheriting paper scores.

[Paper](https://arxiv.org/pdf/2504.19413) · [Repository](https://github.com/mem0ai/mem0). Source snapshot: `26cdefb46600c0fa5953c4b5ee5003c125539fc4`.

<a id="course"></a>
## 16. Course requirements

[Fall 2026 website](https://nlp-course-cuhksz.github.io/) and local Lecture 1, PDF pp.21/27/30/34. The website-linked final-project deck identifies itself as Spring 2026. See the [plan](plan.md#course-deliverables-and-source-conflicts) for source conflicts and submission requirements.

<a id="locomo"></a>
## 17. Evaluating Very Long-Term Conversational Memory of LLM Agents

LoCoMo is a conversational-memory cross-check and a reference point for TierMem. It is optional in EviRecall. Split by complete conversation rather than arbitrary questions; it does not directly measure multi-agent action success.

[Paper](https://arxiv.org/abs/2402.17753) · [Repository](https://github.com/snap-research/locomo).

## Supplementary resources

- [LangGraph](https://github.com/langchain-ai/langgraph): State/checkpoint/store reference supporting the engineering alternative. No separate paper is assigned. Framework persistence alone does not verify semantic correctness of recalled facts.
- [A-MEM paper evaluation implementation](https://github.com/WujiangXu/AgenticMemory): Companion evaluation repository linked by the A-MEM authors. Shares the a-mem.pdf paper; do not count it as a separate paper.
- [ArgusFleet: Governed Shared Memory evaluation harness](https://github.com/caura-ai/argusfleet): Paper-linked evaluation harness: clone returned Repository not found on 2026-10-27. Paper section 6.2 cites trace commit 2c55bb5. Retain this missing artifact in the manifest rather than replacing it with unrelated code.

Dataset releases:

- [LongMemEval cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned)
- [STALE (official 400 scenarios)](https://huggingface.co/datasets/STALEproj/STALE)
- [MAST-Data (paper v3 link)](https://huggingface.co/datasets/mcemri/MAST-Data)
- [MemoryArena](https://huggingface.co/datasets/ZexueHe/memoryarena)
- [MemoryAgentBench](https://huggingface.co/datasets/ai-hyz/MemoryAgentBench)

Availability limits: the paper-linked ArgusFleet repository returned Repository not found; TierMem's separate OpenReview PDF returned HTTP 403. The TierMem arXiv PDF, Jev source, Governed Shared Memory paper, and current Caura source were collected. These are distinct artifacts, not interchangeable reproduction packages.
