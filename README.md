[English](#english) | [简体中文](#简体中文)

<a id="english"></a>

# EviRecall

**Evidence-aware memory for long-horizon multi-agent tasks.** A three-person NLP course project investigating evidence reuse, stale-memory propagation, and recovery under limited resources.

**Stage: M1 execution harness implemented; M2 offline LongMemEval tooling and verified data available locally.** Execution, call accounting, independent scoring, and saved-result summaries have separate commands. All 500 cleaned S tasks load; the candidate grouped split has 327 development and 102 test questions. The large development group requires a separately bounded pilot. Real Smurfs/Jev adapters, the real model/judge pilot, memory intervention, and experiments remain pending. Fixture outputs are wiring checks, not benchmark results. See the [implementation record](docs/implementation-status.md) and [evaluation harness guide](docs/evaluation-harness.md).

Run execution, fixture scoring, and offline summary reconstruction separately. Each output directory must be new:

```bash
python -m evirecall run --config configs/run-fixture.json --output runs/fixture-run
python -m evirecall score runs/fixture-run --expectations fixtures/evaluator/expectations.jsonl --output runs/fixture-scores
python -m evirecall summarize runs/fixture-run --evaluation runs/fixture-scores
```

The `run` configuration selects explicit registered agent and memory backends; unknown names fail before execution output is created. The included configuration uses deterministic fixtures and makes no API calls. Run artifacts retain the planned task IDs, input hashes, per-task results, trace, call ledger, and isolated stores. Scoring runs separately, and missing judgments remain unknown in coverage and success bounds.

For a local LongMemEval JSON file, `prepare-longmemeval SOURCE --revision REVISION --output PREPARED` records provenance and creates separate public tasks and evaluator references; optional `--sha256 HASH` checks the source file. `split-longmemeval PREPARED --output SPLIT` freezes grouped partitions. `export-longmemeval RUN --references REFERENCES --output EXPORTED` creates inputs for the pinned official QA scorer. `import-longmemeval EXPORTED --scores OFFICIAL_RESULTS --output SCORES` replays saved boolean judgments without API calls; explicit `--allow-partial` retains incomplete judging as unknown. These commands do not download the dataset or invoke a paid judge.

M3 preparation now includes bounded one-query-per-group pilot manifests, explicit `module:factory_name` backend loading, read-only `preflight`, and `judge-longmemeval` with a separate `--check` mode and durable call accounting. The actual model pilot remains pending. The [pilot handoff guide](docs/pilot-handoff.md) explains the one-question and ten-question candidate manifests, configuration templates, and provider/budget requirements. Templates use a zero cost threshold; they are not ready-to-spend configurations.

## Quick start

Use Python 3.11 or later (team default: 3.12) and Git. From the repository root:

```bash
python scripts/setup.py
```

This creates `.venv`, copies `.env.example` only when `.env` does not exist, checks Python/SQLite, runs the tests, and executes three synthetic cases. The core setup uses the Python standard library without package downloads or external model calls; judge transport tests use a local HTTP service. Each smoke run creates a new ignored directory under `runs/`, containing `manifest.json`, `trace.jsonl`, `results.jsonl`, `scores.jsonl`, and `summary.json`. Provider usage is unknown/null; fixture checks do not measure model accuracy or stale-memory recovery.

On Windows, run individual commands with:

```powershell
.venv\Scripts\python.exe -m evirecall doctor
.venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m evirecall smoke
```

On macOS/Linux, use `.venv/bin/python` in place of `.venv\Scripts\python.exe`. Activation and editable installation are optional when running from the repository root. Live adapter dependencies will be selected and pinned when those adapters are implemented; the upstream Smurfs and Jev dependency sets are not installed into the core setup automatically.

To prepare the six pinned upstream source repositories on a teammate's machine:

```bash
python scripts/prepare_sources.py --fetch
python -m evirecall doctor --require-upstreams
```

In the existing course workspace, reuse the downloaded snapshots without network access:

```bash
python scripts/prepare_sources.py --from-library ../library
```

The script creates independent checkouts in ignored `vendor/`, verifies commits from [the source lock](configs/upstreams.json), and leaves an existing changed checkout untouched. It does not install or execute upstream code. Full datasets, LFS payloads, weights, and API access remain separate pilot prerequisites. `.env.example` lists future provider variables; the offline path does not load credentials.

## Start here

- **[English proposal](docs/proposal.md)** — research motivation, selection trade-offs, proposed method, experiments, and named work packages. [Submission PDF](output/pdf/EviRecall_Project_Proposal.pdf) · [LaTeX](docs/proposal.tex).
- **[Execution plan](docs/plan.md)** — ownership, shared interfaces, milestones, report assembly, and verified course requirements.
- **[Team handoff register](docs/team-handoff.md)** — concrete deliverables, owners, pilot dependencies, and integration acceptance (Chinese).
- **[Git and PR collaboration guide](docs/collaboration.md)** — branch setup, reviewing an unmerged PR, and starting the next task (Chinese).

The [reference index](docs/references.md) and [BibTeX](docs/references.bib) support these two documents. Earlier Chinese documents are historical material in [archive](archive/README.md).

## Three work packages

1. **Xiaochen Bai — Memory and Smurfs:** own `evirecall/memory/` and `evirecall/agents/`; build the Jev adapter, Smurfs hooks, intervention, and ablations.
2. **Bijun Zeng — Evidence and errors:** own `evirecall/tasks/`, `fixtures/`, and `evirecall/evaluation/errors/`; build task adapters, evidence labels, and error/recovery analysis.
3. **Chengyu Tang — Benchmark and resources:** own `evirecall/runner/`, score wrappers, CLI, and `configs/`; build reproducible evaluation, usage accounting, and budget/load measurements.

Each member owns code, experiments, analysis, and report sections. The [shared contracts](evirecall/contracts.py) define `TaskInput`, `MemoryBackend`, `EvidencePacket`, `AgentOutput`, `TraceEvent`, and `EpisodeResult`. Public inputs live in `fixtures/public/`; evaluator expectations live separately in `fixtures/evaluator/`. The fixture agent only echoes recent observations and is explicitly labeled in every run.

Start a branch such as `feat/memory-smurfs`, `feat/evidence-errors`, or `feat/benchmark-runner`, make a small PR, and have another member review it. Changes to contracts or shared fixtures need review from both other owners. The [execution plan](docs/plan.md#first-parallel-implementation-tasks) gives each owner a first task and integration boundary.

The [GitHub Actions template](ci/offline-checks.yml) configures offline checks on Linux/Python 3.11 and Windows/Python 3.12. It is not active: the current GitHub credential lacks permission to publish workflow files. Once an authorized maintainer copies it to `.github/workflows/ci.yml`, pushes and PRs will trigger those checks. Until then, run the local setup checks before merging. Local Windows/Python 3.12 checks passed on 28 October 2026; Linux CI has not yet been verified.

Proposed evaluations: cleaned LongMemEval_S and STALE, plus a small MemoryArena action pilot. Existing data are reused; version 1 does not require model training. Dataset availability and final scope are documented in the plan.

## Documents and local resources

Earlier workspace notes refer to a sibling `../library/` directory for downloaded papers and upstream source snapshots. That directory is absent from the current checkout environment; prepare the pinned sources with `scripts/prepare_sources.py --fetch` when needed. Large datasets, model weights, and third-party repositories are not bundled in this project repository.

Edit `docs/proposal.md` and `docs/references.bib`, then regenerate the editable LaTeX/PDF with Python and an existing XeLaTeX installation:

```bash
python scripts/build_proposal.py --pdf
```

The proposal uses connected prose to explain the alternatives and trade-offs, with tables for the team roster and responsibilities. The roster is populated in the Markdown source; its personal details and email links render in blue. Use blank lines for separate paragraphs. The generator also supports standalone headings, `<br>` within table cells, and explicit page breaks.

The proposal is finalized for submission to [Natural Language Processing (CSC5051 / CSC6052 / MDS5110), Fall 2026](https://nlp-course-cuhksz.github.io/). The generated PDF uses a stable filename without a draft version number.

## 简体中文

EviRecall 是三人合作的自然语言处理课程项目，研究长程多智能体任务中的证据复用、过期记忆传播和资源受限下的恢复。项目背景、方法与实验设计见[英文提案](docs/proposal.md)（[提交 PDF](output/pdf/EviRecall_Project_Proposal.pdf) · [LaTeX](docs/proposal.tex)），分工与里程碑见[执行计划](docs/plan.md)。[参考文献索引](docs/references.md)和 [BibTeX](docs/references.bib)提供相关资料，早期中文文档保留在[归档](archive/README.md)。

**当前状态：M1 运行底座已实现，M2 离线工具与完整 LongMemEval 数据已在本地验证。** 500 道 cleaned S 题目全部可加载，候选分组划分得到开发集 327 题、测试集 102 题；开发集包含大型连通组，pilot 必须另行限制题量。已提供独立执行、逐调用记账、评分和结果复算，以及官方评分输入导出和已保存评分回放。真实 Smurfs/Jev 适配器、真实模型与 judge 小规模闭环、记忆干预和正式实验仍待开展。合成 fixture 仅验证工程接线，不能作为 benchmark 效果的证据。详见[实施记录](docs/implementation-status.md)与[评测底座说明](docs/evaluation-harness.md)。

### 安装与离线运行

使用 Python 3.11 或更新版本（团队默认 3.12）和 Git，在仓库根目录执行：

```bash
python scripts/setup.py
```

安装脚本创建 `.venv`，仅在 `.env` 不存在时复制 `.env.example`，检查环境并运行测试与三个合成案例。核心流程使用 Python 标准库，不下载依赖或调用外部模型；judge 传输测试使用本地 HTTP 服务。Windows 可使用 `.venv\Scripts\python.exe` 替代下方的 `python`；macOS/Linux 使用 `.venv/bin/python`。

```bash
python -m evirecall doctor
python -m unittest discover -s tests -v
python -m evirecall smoke
python -m evirecall run --config configs/run-fixture.json --output runs/fixture-run
python -m evirecall score runs/fixture-run --expectations fixtures/evaluator/expectations.jsonl --output runs/fixture-scores
python -m evirecall summarize runs/fixture-run --evaluation runs/fixture-scores
```

输出目录必须是新目录；重复运行时请更换名称。`run` 使用显式配置的 agent/memory 后端，未知后端直接拒绝；默认配置仅运行 fixture，不调用真实服务。执行与评分分开保存，可在不重新执行任务、不调用 judge 的情况下重算汇总。运行产物保留固定任务清单、输入 hash、逐题结果、调用账本、trace 和隔离存储；失败任务与未完成评分分别统计，未知评分不会被自动记为错误答案。

### LongMemEval 离线工具

以下命令处理已有的本地 JSON 数据，不自动下载数据，也不发起付费评分请求：

```bash
python -m evirecall prepare-longmemeval PATH_TO_LOCAL_JSON --revision DATA_REVISION --output data/prepared
python -m evirecall split-longmemeval data/prepared --output data/split --dev-units 10 --test-questions 100 --seed 0
python -m evirecall export-longmemeval RUN_DIRECTORY --references EVALUATOR_REFERENCES_JSONL --output runs/judge-inputs
python -m evirecall import-longmemeval runs/judge-inputs --scores OFFICIAL_RESULTS_JSONL --output runs/judge-replay
```

转换时可添加 `--sha256 HASH` 核验本地源文件。公开输入与包含答案的 evaluator 文件分开，分组划分用于防止共享历史或证据跨集合。评分回放遵循固定版本官方脚本的布尔标签；如需回放中断后的部分评分，显式添加 `--allow-partial`，剩余评分保留为未知并报告成功率上下界。正式数据版本、划分、模型、预算和实验规模仍需冻结与核查。

### M3 接入准备

已增加每组最多一题的有限 pilot 清单、`module:factory_name` 后端入口、只读 `preflight`，以及带 `--check` 模式和独立账本的 `judge-longmemeval`。1 题和 10 题候选清单均已在本地生成，尚未运行真实模型。配置模板使用零费用阈值；后端位置、服务与预算仍需按实际交付填写。操作步骤、摄入规模及限制见 [M3 交接说明](docs/pilot-handoff.md)。

### 分工与交接边界

[团队交接登记](docs/team-handoff.md)逐项记录负责人、具体产物、分支/PR/commit、验收与集成状态；[Git 与 PR 协作指南](docs/collaboration.md)提供从新分支、评审到合并的操作步骤。首次真实 LongMemEval pilot 依赖 Xiaochen 的真实 backend 与调用 hooks、Chengyu 的配置和资源准备；Bijun 的 STALE/MemoryArena 交付并行推进，不阻塞该 pilot。

- **Xiaochen Bai：记忆与 Smurfs。** 负责 `evirecall/memory/`、`evirecall/agents/`、Jev 适配器、Smurfs 接入、干预和消融。
- **Bijun Zeng：证据与错误分析。** 负责任务协议、数据与环境交接、证据标签、错误和恢复分析，以及 `evirecall/evaluation/errors/`。
- **Chengyu Tang：评测与资源。** 负责 `evirecall/runner/`、评分封装、CLI、配置、公共 LongMemEval 加载与评分交接、可复现运行、调用费用和预算测量。

公共接口见 [contracts.py](evirecall/contracts.py)。评测底座不替代真实方法适配器、STALE 数据核查或 MemoryArena 环境交付；每位成员仍负责自己的代码、实验、分析和报告部分。公共 schema 或跨模块语义变更需要共同评审。

早期工作区说明中的 `../library/` 在当前环境不存在。项目不打包大型数据集、模型权重或第三方仓库。需要准备固定版本源码时，可运行 `python scripts/prepare_sources.py --fetch`；只有本地确有源码库时才使用 `--from-library ../library`。具体固定版本见[源码锁定清单](configs/upstreams.json)。源码准备不等于数据、依赖或真实服务已可用。
