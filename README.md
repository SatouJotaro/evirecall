# EviRecall

**Evidence-aware memory for long-horizon multi-agent tasks.** A three-person NLP course project investigating evidence reuse, stale-memory propagation, and recovery under limited resources.

**Stage: proposal and source review.** Smurfs is the selected backbone; Jev TierMem is the first memory candidate. The intervention, experiment scale, and action environment remain subject to a feasibility pilot. This repository does not yet contain a working EviRecall agent or measured improvements.

## Start here

- **[English proposal](docs/proposal.md)** — agents/memory/data comparisons, model and integration choices, planned work, experiments, and three work packages. [PDF](output/pdf/evirecall-proposal-v0.4.pdf) · [LaTeX](docs/proposal.tex).
- **[Execution plan](docs/plan.md)** — ownership, shared interfaces, milestones, report assembly, and verified course requirements.

The [reference index](docs/references.md) and [BibTeX](docs/references.bib) support these two documents. Earlier Chinese documents are historical material in [archive](archive/README.md).

## Three work packages

1. **Memory:** Jev adapter, Smurfs hooks, one intervention, and mechanism ablations.
2. **Evidence and errors:** task scenarios, source-support analysis, stale-information propagation, and recovery experiments.
3. **Benchmark:** shared runner, reproducible evaluation, usage accounting, and budget/load measurements.

Each member owns code, experiments, analysis, and report sections. Interfaces and a small integrated example come first; the report uses one shared protocol and joint conclusions.

Proposed evaluations: cleaned LongMemEval_S and STALE, plus a small MemoryArena action pilot. Existing data are reused; version 1 does not require model training. Dataset availability and final scope are documented in the plan.

## Documents and local resources

The local workspace keeps downloaded papers and upstream source snapshots in the sibling `../library/` directory, outside this Git repository. Its `README.md` is the local reading index; `manifest.json` records source URLs, PDF hashes, and repository commits. Large datasets, model weights, and third-party repositories are not bundled in this project repository.

Edit `docs/proposal.md` and `docs/references.bib`, then regenerate the editable LaTeX/PDF with Python and an existing XeLaTeX installation:

```bash
python scripts/build_proposal.py --pdf
```

The PDF uses blue clickable source links and blue personal-detail placeholders. Edit the `{{...}}` fields in the Markdown source to fill in each member's name, student ID, and university email. Use blank lines for separate paragraphs, `####` for standalone labels, and `<br>` for intentional line breaks within table cells. These structures and explicit page breaks are preserved by the generator.

The generated proposal is a working document. Apply the course's confirmed submission template before submission. Course: [CSC5051 / CSC6052 / MDS5110, Fall 2026](https://nlp-course-cuhksz.github.io/).
