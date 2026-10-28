"""Shared entry point: python -m evirecall doctor|smoke."""

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
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            report = doctor()
            print(json.dumps(report, indent=2))
            ok = report["python_supported"] and report["sqlite_fts5"]
            if args.require_upstreams:
                ok = ok and all(value == "ready" for value in report["upstreams"].values())
            return 0 if ok else 1
        directory, summary = run_config(args.config.resolve(), args.output)
        print(json.dumps({"output": str(directory), **summary}, indent=2))
        return 0 if summary["fixture_checks_passed"] == summary["fixture_checks_total"] else 1
    except (ContractError, OSError, json.JSONDecodeError, TypeError) as exc:
        print(f"Setup error: {exc}", file=sys.stderr)
        return 2
