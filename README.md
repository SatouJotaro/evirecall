# EviRecall

**Evidence-aware memory for long-horizon multi-agent tasks.** A three-person NLP course project investigating evidence reuse, stale-memory propagation, and recovery under limited resources.

**Stage: proposal finalized; offline setup ready.** Shared contracts, synthetic fixtures, an offline runner, and environment/source checks support parallel development. Smurfs/Jev integration, dataset experiments, and the memory intervention remain to be implemented. Setup outputs are not research results.

## Quick start

Use Python 3.11 or later (team default: 3.12) and Git. From the repository root:

```bash
python scripts/setup.py
```

This creates `.venv`, copies `.env.example` only when `.env` does not exist, checks Python/SQLite, runs the tests, and executes three synthetic cases. The core setup uses the Python standard library and makes no API calls or package downloads. Each run creates a new ignored directory under `runs/`, containing `manifest.json`, `trace.jsonl`, `results.jsonl`, `scores.jsonl`, and `summary.json`. Provider usage is unknown/null; fixture checks do not measure model accuracy or stale-memory recovery.

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
- **[Team discussion questionnaire](docs/discussion.html)** — Chinese offline form covering scope, resources, error definitions, experiments, and collaboration. Download the HTML and open it in a browser; each member can save a separate draft, export JSON/Markdown, and import the three JSON answers for comparison. Choices start blank and do not modify the agreed plan automatically.

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

The local workspace keeps downloaded papers and upstream source snapshots in the sibling `../library/` directory, outside this Git repository. Its `README.md` is the local reading index; `manifest.json` records source URLs, PDF hashes, and repository commits. Large datasets, model weights, and third-party repositories are not bundled in this project repository.

Edit `docs/proposal.md` and `docs/references.bib`, then regenerate the editable LaTeX/PDF with Python and an existing XeLaTeX installation:

```bash
python scripts/build_proposal.py --pdf
```

The proposal uses connected prose to explain the alternatives and trade-offs, with tables for the team roster and responsibilities. The roster is populated in the Markdown source; its personal details and email links render in blue. Use blank lines for separate paragraphs. The generator also supports standalone headings, `<br>` within table cells, and explicit page breaks.

The proposal is finalized for submission to [Natural Language Processing (CSC5051 / CSC6052 / MDS5110), Fall 2026](https://nlp-course-cuhksz.github.io/). The generated PDF uses a stable filename without a draft version number.

The questionnaire is a single self-contained HTML file with no external dependencies or online submission. Its content lives in `scripts/questionnaire_data.json`, its layout and interactions in `scripts/questionnaire.template.html`; regenerate with `python scripts/build_questionnaire.py`. Drafts are stored in the current browser when local storage is available. Export JSON before moving the file or changing browsers. Imported comparisons are discussion aids; record agreed decisions in `docs/plan.md` after the meeting.
