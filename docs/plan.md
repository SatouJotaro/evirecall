# EviRecall execution plan

Proposal finalized for submission on 28 October 2026. Research design: [English proposal](proposal.md). Upstream links and selection notes: [references](references.md). The shared contracts and offline fixture path are implemented; live adapters and scientific experiments remain work for their owners.

## Scope to freeze after the pilot

- Fixed: Smurfs as the agent backbone; evidence-aware memory as the research focus; one shared experimental protocol.
- Proposed: Jev as the first memory backend; LongMemEval_S and STALE as primary memory evaluations; a small MemoryArena travel study for downstream actions.
- Week-1 decisions: actual providers and costs; Jev access; CUP-Mem feasibility; task-environment availability; development/test grouping; one intervention and one model configuration.
- Optional extensions: learned routing, implicit-conflict detection, another framework, GPU-serving experiments. None is a prerequisite for the main comparison.

## Implementation choices and pending decisions

The proposal compares agents, memory methods, and evaluation resources, then records five implementation choices. These are design decisions, not measured wins over the alternatives.

- **Model/provider:** start with a configurable API client and a fixed task/answer model across conditions. Select the exact provider, model/version, and spending cap after pilot access, tool-call, context, and cost checks. Record Jev's separate judgment service and evaluation models.
- **Integration:** use a direct Python adapter initially. MCP/HTTP service boundaries remain optional; Smurfs generates answers and receives evidence in its verifier. Jev write-back is explicit.
- **Storage/retrieval:** reuse Jev's SQLite/FTS5 raw store and file-based summaries, with adapter-owned update/validity metadata. Serialize writes within groups and isolate conditions. Adding a vector database or shared service is outside the minimum scope.
- **Tool environment:** pilot one MemoryArena travel adapter, including database access and a complete multi-session trace. If unavailable, retain controlled cross-role tests and narrow action claims.
- **Evaluation/execution:** use official score wrappers, evidence/recovery annotations, and human checks. Chengyu owns a Python runner with versioned configurations, JSONL traces, and CSV summaries. Freeze judges and sampling rules; parallelize independent groups. External tracking services and GPU scheduling are optional.

The week-1 freeze must resolve model/provider access, Jev access, CUP-Mem feasibility, action environment, dataset IDs, budget limits, and scoring configuration. Each member retains freedom over internal implementation within the shared interfaces.

## Three owners, with comparable deliverables

The agreed owners are Xiaochen Bai for memory/Smurfs, Bijun Zeng for evidence/errors, and Chengyu Tang for evaluation/resources. Work package numbers refer to responsibilities, independently of roster order.

### 1. Xiaochen Bai: memory method and Smurfs hooks

Own `evirecall/memory/` and `evirecall/agents/`, including the small memory-related changes in the Smurfs adapter. Deliver four bounded pieces: recent-history/BM25/Jev adapters; read/write/verifier hooks; one explicit-update intervention; mechanism ablations and analysis. Xiaochen owns baseline memory behavior, not the entire benchmark runner.

Acceptance: returned evidence resolves to immutable records; a summary cannot gain authority solely from agent agreement; invalidation behavior can be inspected on fixtures; disabling each mechanism produces a documented ablation. Write the method and ablation sections, with one architecture figure and a quality/cost comparison.

### 2. Bijun Zeng: evidence, task environments, and error analysis

Own `evirecall/tasks/`, the travel-tool adapter, `fixtures/`, and `evirecall/evaluation/errors/`. Deliver four bounded pieces: the STALE input/label separation specification; paired update/no-update cases; a small action-task pilot; trace-level evidence and recovery analysis. Reuse the official STALE release and existing MemoryArena tools instead of authoring a new general benchmark.

Acceptance: cases have source IDs, update points, expected valid constraints, and evaluator-only labels; a trace scorer runs on fixtures without Xiaochen's module; two reviewers independently annotate a prespecified sample; disagreements and failures are retained. Write task/intervention design and qualitative/error results. Own the scientific meaning of an error, while Chengyu owns execution and aggregation.

### 3. Chengyu Tang: benchmark harness and resource experiments

Own `evirecall/evaluation/` score wrappers, `evirecall/runner/`, the CLI, and experiment configurations. Bijun owns the evidence/error definitions within `evaluation/errors/`. Deliver four bounded pieces: memory-QA loading and official-score wrappers; a common runner with isolated stores; complete usage/latency/failure accounting; a small budget/concurrency study and reproducibility package. Chengyu calls Xiaochen's agent/memory adapter and Bijun's task adapter instead of implementing both.

Acceptance: the same configuration switches memory methods; failures stay in denominators; summaries recompute from saved events; retries and queue time are counted; unavailable provider usage is marked unknown. Write common experimental setup and systems results. API-level load experiments are sufficient; Kubernetes, a distributed scheduler, dashboards, and a new serving stack are out of scope.

These are equal categories of responsibility, not a claim of measured equal effort. At the end of week 1, compare estimated remaining work and transfer a bounded adapter or scorer if needed. Protect balance by limiting Bijun to one action environment and Chengyu to one runner plus two resource axes. Each member runs and explains their own experiments through the shared runner.

## Shared contracts and offline setup

The initial contract is implemented in `evirecall/contracts.py`, with three synthetic fixtures for ordinary recall, explicit update, and insufficient evidence. Each owner may choose their internal implementation; changes to shared fields require review by the other two owners.

- **Task input:** `dataset`, `task_id`, `group_id`, `session_id`, ordered public events, `query`, and permitted `tools`. `TaskInput.from_dict()` rejects unexpected fields. Gold answers, `has_answer`, `answer_session_ids`, STALE explanations, and environment ground truth are evaluator-only.
- **Memory operations:** `observe(event)`, `summarize(source_ids)`, `retrieve(query, budget)`, `apply_update(event)`, and `reset(scope)`. The adapter translates these to Jev; they are not claims about Jev's native API.
- **Evidence packet:** text, raw/source IDs, writer role, event time, validity/review state, retrieval route, and usage. A version or an ID existing does not prove semantic support.
- **Trace event:** schema version, run/condition/group/session IDs, step, role, operation, input/output references, cited IDs, budget, timing, usage, terminal status/error. The initial `TraceEvent` has run/task correlation fields plus an operation name and JSON payload; the payload holds observations, evidence packets, usage, and terminal results. Log observable inputs, outputs, and actions; do not require private model reasoning.
- **Episode result:** prediction or final plan, terminal status, evidence references, trace path, and total usage. Bijun's scorer and the official evaluator add labels after execution.

One run owns one store namespace. Preserve history within an intended multi-session group; reset between groups and conditions. Serialize writes within a group initially. Chengyu may execute independent groups concurrently, with isolation checks.

Jev's Python flow is `observe` → source-linked `add_summary` → `retrieve`; Smurfs then answers. A separate explicit `promote` can write recovered evidence back. The paper's trained router and Jev's judgment service are different systems. Do not label a heuristic replacement as unmodified Jev, or omit its judgment calls from cost accounting.

## First parallel implementation tasks

The offline path is `TaskInput -> FixtureAgent -> FixtureMemory -> EpisodeResult -> fixture evaluator`. It checks integration only: the agent echoes the most recent observation, and the memory stub neither summarizes nor invalidates evidence. Synthetic update cases are wiring fixtures, not proof of stale-memory recovery. The entry point is `python -m evirecall smoke`; setup and source preparation commands are in the repository README.

Xiaochen's first task is a Smurfs adapter under `evirecall/agents/` that accepts `TaskInput` and returns `AgentOutput`, with memory access through `MemoryBackend` and observable events through `emit`. Start with one real development task and an unchanged baseline before adding the proposed intervention. The six upstream source revisions are pinned in `configs/upstreams.json`; live provider/dependency choices must be recorded when selected.

Bijun's first task is conversion of a small STALE development sample into public tasks and a separate evaluator file, followed by a scorer that can analyze saved traces independently of a live agent. In parallel, check the MemoryArena travel database and tool interface. Keep official scores and custom stress-suite scores distinct. Dataset-specific gold fields must not be added to `TaskInput`.

Chengyu's first task is extending the fixture-only CLI to an explicit backend registry, adding memory-QA data/score wrappers, and defining complete provider usage accounting. Unsupported backend names currently fail rather than falling back to the fixture. Preserve grouping, failure records, input hashes, and separate evaluator data when extending the runner; add concurrency only after the single-task path is reproducible.

All three begin with a small branch and a PR that passes the offline checks. Each member runs their own experiment configurations. Review schema changes together and integrate at least weekly; a temporary fixture interface is sufficient to unblock another member before a live backend is complete.

## Experiments and dependencies

**Memory QA:** Xiaochen supplies backends; Bijun specifies which STALE fields can reach the model; Chengyu loads the public input, dispatches identical questions, and invokes official scoring. LongMemEval and STALE measure different abilities but share some source histories. Check overlap across development/test groups and disclose cross-dataset dependence. No parameter training is required for version 1.

**Cross-role reliability:** Bijun chooses interventions and annotation rules; Xiaochen exposes source/validity state at Smurfs role handoffs; Chengyu captures events. Separate an explicit structured-update suite from STALE's implicit conflicts. Metadata-only invalidation must not receive gold conflict explanations. Keep ordinary memory QA separate from genuine multi-agent task execution.

**Action pilot:** Bijun connects one MemoryArena travel environment; Xiaochen supplies Smurfs+memory; Chengyu runs all conditions. The repository is marked preview and requires a separately downloaded flight database. Success means one complete multi-session group with lawful observations, correct evaluator boundaries, and measured cost. Attempt this during week 1, before committing to the 20-group target. If blocked, retain two memory benchmarks and controlled cross-role episodes, rename claims accordingly, and report that end-to-end long-horizon action was not evaluated.

**Resource study:** Chengyu varies at most three predeclared evidence budgets and concurrency 1/2/4 on a fixed subset. Xiaochen helps interpret retrieval costs; Bijun checks whether stale-evidence errors increase. Run each axis separately unless a specific interaction warrants a small follow-up. An evidence budget is a resource limit, not a GPU scheduler.

For every run save code/upstream commits, dataset revision and IDs, configuration, prompts, model/judge versions, tokenization assumptions, seed, per-episode status, and source-linked trace. Keep development and final test manifests separate. Run paired conditions on the same units. Cluster uncertainty calculations by shared history/scenario/task group and show sample counts. With small load samples, label P95 as descriptive rather than a stable service guarantee.

## Integration and report assembly

1. **Week 1:** agree on fixtures and contracts. Xiaochen provides a dummy backend and one Smurfs task, Bijun provides a fixed trace and task fixture, Chengyu runs them end to end. Freeze provider costs and minimum scope together.
2. **Weeks 2-3:** integrate at least weekly. Use separate branches and small PRs. Xiaochen reviews Bijun's source/label boundaries; Bijun reviews Chengyu's denominators; Chengyu reviews Xiaochen's interface and accounting. Freeze test data before final tuning ends.
3. **Week 4:** each owner executes their experiments through the same runner and contributes figures plus the commands and logs behind them. Share one named configuration for the main result.
4. **Week 5:** one other member reproduces each main result. Each author writes their assigned sections; a rotating editor removes repetition and resolves conflicting terminology, setup, and conclusions. All three review the final paper and rehearse explaining another member's module.

Report structure: introduction/research questions; related work; method (Xiaochen); datasets and task design (Bijun); shared experimental setup (Chengyu, reviewed by all); method ablations (Xiaochen), evidence/error results (Bijun), resource results (Chengyu); joint limitations/conclusion; individual contributions and references. Assemble around the same questions and evidence, rather than concatenating three self-contained reports.

## Course deliverables and source conflicts

Checked 27 October 2026 against the local **Lecture 1: Introduction**, PDF pages 21, 27, 30, and 34, and the [Fall 2026 course website](https://nlp-course-cuhksz.github.io/).

- Final report: LaTeX; Lecture 1 p.21 says **at most six pages of main body**. The current website says max six pages without clarifying reference treatment. Use the [currently linked template](https://www.overleaf.com/read/fvhykwvngdwz) and confirm final page-count wording when the Fall project brief is released.
- Poster and oral presentation; source code submitted in GitHub; individual contribution statement (Lecture 1 p.34). A deployed service, original dataset, trained model, or formal paper acceptance is not established as a required deliverable by these sources.
- Current website grading: project 55%, comprising poster presentation 10% and report 45%. It asks for related work, a sound protocol, quantitative and qualitative results, and individual contributions.
- Current Fall website calendar: optional proposal/team formation **13 November**; poster **17 December, 17:00**; presentation **18 December**; report **25 December, 23:59**. These are website-listed dates, subject to later course/Blackboard notices.
- Lecture 1 p.27 retains March/May dates and a one-page proposal suggestion; p.30 gives a tentative 1 November proposal date and says custom topics need approval. The current website lists proposal as optional for feedback. Submit this custom topic for instructor/TA feedback; do not interpret the older page as a final Fall deadline or confirmed current proposal-length rule.
- The website's final-project slides link currently opens **Spring 2026** slides. Their 15%/40% split, four-minute presentation, May deadlines, BB submission details, and older template must not be silently imported into Fall requirements. Those sources are preserved in the local library for comparison.

The English proposal and team roster are finalized for submission. Implementation will follow the shared contracts and feasibility checks above.

## Decision history

The team moved from a broad multi-agent reliability topic to memory, evidence/error recovery, and resource evaluation. Smurfs became the selected backbone; Jev became the first integration candidate. Version 0.2 adds STALE/CUP-Mem to the closest-work comparison, makes two memory evaluations explicit, limits the action study to a pilot, and changes responsibilities to memory / evidence-and-errors / benchmark. Earlier discussion and the superseded Chinese proposal are preserved under `archive/proposal-v0.1/`.

Version 0.4 records the model/provider, integration boundary, storage/retrieval, tool environment, and evaluation/execution choices alongside the research comparisons. It distinguishes selected directions from pilot-dependent configuration and uses explicit paragraph, heading, and table-cell breaks.

Version 0.5 presents the proposal as a connected research argument, expands the reasons and trade-offs behind the selections, and fills the roster with named proposed owners. The evaluation scope and implementation boundaries remain those defined above.

On 28 October 2026, the team confirmed the ownership change: Xiaochen Bai leads memory/Smurfs, Bijun Zeng leads evidence/errors, and Chengyu Tang leads evaluation/resources. Shared contracts, offline fixtures, and setup checks now support parallel implementation.
