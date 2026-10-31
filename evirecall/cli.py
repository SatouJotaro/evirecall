"""Execution, independent scoring, dataset preparation, and diagnostics."""

import argparse
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from evirecall.contracts import ContractError
from evirecall.runner.smoke import ROOT, run_config


def doctor() -> dict:
    with sqlite3.connect(":memory:") as connection:
        try:
            connection.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
            fts5 = True
        except sqlite3.OperationalError:
            fts5 = False
    lock = json.loads((ROOT / "configs/upstreams.json").read_text(encoding="utf-8"))
    sources = {}
    for item in lock["sources"]:
        path = ROOT / "vendor" / item["id"]
        if not (path / ".git").exists():
            sources[item["id"]] = "missing"
            continue
        try:
            actual = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"],
                                    capture_output=True, text=True, check=True).stdout.strip()
            dirty = subprocess.run(["git", "-C", str(path), "status", "--porcelain"],
                                   capture_output=True, text=True, check=True).stdout != ""
            sources[item["id"]] = "ready" if actual == item["commit"] and not dirty else "changed"
        except (OSError, subprocess.CalledProcessError):
            sources[item["id"]] = "unreadable"
    return {"python": sys.version.split()[0], "python_supported": sys.version_info >= (3, 11),
            "sqlite_fts5": fts5, "local_env_file": (ROOT / ".env").is_file(),
            "upstreams": sources, "live_api_tested": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    health = commands.add_parser("doctor", help="Check Python, SQLite, and optional pinned source checkouts")
    health.add_argument("--require-upstreams", action="store_true")
    smoke = commands.add_parser("smoke", help="Run three synthetic fixtures without any API calls")
    smoke.add_argument("--config", type=Path, default=ROOT / "configs/smoke.json")
    smoke.add_argument("--output", type=Path, help="A new output directory; existing directories are refused")
    run = commands.add_parser('run', help='Execute explicit configured backends without scoring')
    run.add_argument('--config', type=Path, default=ROOT / 'configs/run-fixture.json')
    run.add_argument('--output', type=Path, required=True)
    preflight = commands.add_parser('preflight', help='Inspect task/config/backend wiring without constructing a backend')
    preflight.add_argument('--config', type=Path, default=ROOT / 'configs/run-fixture.json')
    score = commands.add_parser('score', help='Independently score saved fixture execution')
    score.add_argument('run', type=Path)
    score.add_argument('--expectations', type=Path, required=True)
    score.add_argument('--output', type=Path)
    summarize = commands.add_parser('summarize', help='Recompute saved execution and evaluation summaries')
    summarize.add_argument('run', type=Path)
    summarize.add_argument('--evaluation', type=Path)
    prepare = commands.add_parser('prepare-longmemeval', help='Prepare local pinned LongMemEval source')
    prepare.add_argument('source', type=Path)
    prepare.add_argument('--revision', required=True)
    prepare.add_argument('--sha256')
    prepare.add_argument('--output', type=Path, required=True)
    split = commands.add_parser('split-longmemeval', help='Freeze grouped LongMemEval partitions')
    split.add_argument('prepared', type=Path)
    split.add_argument('--output', type=Path, required=True)
    split.add_argument('--dev-units', type=int, default=10)
    split.add_argument('--test-questions', type=int, default=100)
    split.add_argument('--seed', type=int, default=0)
    pilot = commands.add_parser('prepare-pilot', help='Select bounded dev questions with at most one per protected group')
    pilot.add_argument('prepared', type=Path)
    pilot.add_argument('--split', type=Path, required=True)
    pilot.add_argument('--output', type=Path, required=True)
    pilot.add_argument('--max-questions', type=int, default=1)
    pilot.add_argument('--seed', type=int, default=0)
    export = commands.add_parser('export-longmemeval', help='Export official QA judge inputs without API calls')
    export.add_argument('run', type=Path)
    export.add_argument('--references', type=Path, required=True)
    export.add_argument('--output', type=Path, required=True)
    replay = commands.add_parser('import-longmemeval', help='Replay saved official QA judgments without API calls')
    replay.add_argument('prepared', type=Path)
    replay.add_argument('--scores', type=Path, required=True)
    replay.add_argument('--output', type=Path, required=True)
    replay.add_argument('--allow-partial', action='store_true')
    judge = commands.add_parser('judge-longmemeval', help='Inspect or run a bounded official-protocol judge')
    judge.add_argument('prepared', type=Path)
    judge.add_argument('--config', type=Path, required=True)
    judge_mode = judge.add_mutually_exclusive_group(required=True)
    judge_mode.add_argument('--check', action='store_true', help='Validate locally without sending HTTP requests')
    judge_mode.add_argument('--output', type=Path, help='New evaluator output directory for actual judge execution')
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            report = doctor()
            print(json.dumps(report, indent=2))
            ok = report["python_supported"] and report["sqlite_fts5"]
            if args.require_upstreams:
                ok = ok and all(value == "ready" for value in report["upstreams"].values())
            return 0 if ok else 1
        if args.command != 'smoke':
            if args.command == 'run':
                from evirecall.runner.config import run_config as execute_config
                summary = execute_config(args.config, args.output)
            elif args.command == 'preflight':
                from evirecall.runner.config import inspect_config
                summary = inspect_config(args.config)
            elif args.command == 'score':
                from evirecall.evaluation.scoring import score_run
                directory, summary = score_run(args.run, args.expectations, output_dir=args.output)
                summary = {'output': str(directory), **summary}
            elif args.command == 'summarize':
                from evirecall.evaluation.aggregate import summarize_run
                summary = summarize_run(args.run, args.evaluation)
            elif args.command == 'prepare-longmemeval':
                from evirecall.tasks.longmemeval import prepare_dataset
                summary = prepare_dataset(args.source, args.output, revision=args.revision, expected_sha256=args.sha256)
            elif args.command == 'split-longmemeval':
                from evirecall.tasks.longmemeval import build_split
                summary = build_split(args.prepared, args.output, dev_units=args.dev_units,
                                      test_questions=args.test_questions, seed=args.seed)
            elif args.command == 'prepare-pilot':
                from evirecall.tasks.pilot import prepare_pilot
                summary = prepare_pilot(args.prepared, args.split, args.output,
                                        max_questions=args.max_questions, seed=args.seed)
            elif args.command == 'export-longmemeval':
                from evirecall.evaluation.longmemeval import export_predictions
                summary = export_predictions(args.run, args.references, args.output)
            elif args.command == 'judge-longmemeval':
                from evirecall.evaluation.judge import inspect_judge_config, run_judge
                summary = inspect_judge_config(args.prepared, args.config) if args.check else run_judge(
                    args.prepared, args.config, args.output)
            else:
                from evirecall.evaluation.longmemeval import import_scores
                summary = import_scores(args.prepared, args.scores, args.output, allow_partial=args.allow_partial)
            print(json.dumps(summary, indent=2))
            return 0
        directory, summary = run_config(args.config.resolve(), args.output)
        print(json.dumps({"output": str(directory), **summary}, indent=2))
        return 0 if summary["fixture_checks_passed"] == summary["fixture_checks_total"] else 1
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2
