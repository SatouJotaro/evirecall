"""Create independent pinned source checkouts. Never install or execute upstream code."""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def git(*args: str, capture: bool = False) -> str:
    result = subprocess.run(["git", *args], cwd=ROOT, check=True, text=True,
                            capture_output=capture,
                            env={**os.environ, "GIT_LFS_SKIP_SMUDGE": "1"})
    return result.stdout.strip() if capture else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-library", type=Path, help="Reuse existing <library>/repos/<id> snapshots offline")
    source.add_argument("--fetch", action="store_true", help="Clone the official repositories over the network")
    parser.add_argument("--only", nargs="+", help="Limit preparation to the named source IDs")
    args = parser.parse_args()
    lock = json.loads((ROOT / "configs/upstreams.json").read_text(encoding="utf-8"))
    sources = lock["sources"]
    if args.only:
        unknown = set(args.only) - {item["id"] for item in sources}
        if unknown:
            parser.error(f"Unknown source IDs: {sorted(unknown)}")
        sources = [item for item in sources if item["id"] in args.only]
    destination_root = ROOT / "vendor"
    destination_root.mkdir(exist_ok=True)
    for item in sources:
        name, commit, url = item["id"], item["commit"], item["url"]
        if not re.fullmatch(r"[a-z][a-z0-9-]*", name) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise SystemExit("Invalid source lock entry")
        if not url.startswith("https://github.com/"):
            raise SystemExit("Expected an official GitHub source URL")
        destination = destination_root / name
        if destination.exists():
            if not (destination / ".git").exists():
                raise SystemExit(f"Refusing to overwrite existing non-checkout directory: {destination}")
            actual = git("-C", str(destination), "rev-parse", "HEAD", capture=True)
            dirty = git("-C", str(destination), "status", "--porcelain", capture=True)
            if actual != commit or dirty:
                raise SystemExit(f"Existing {name} differs from the lock or has changes; left untouched.")
            print(f"{name}: already pinned at {commit[:12]}", flush=True)
            continue
        if args.from_library:
            source_path = (args.from_library / "repos" / name).resolve()
            if not (source_path / ".git").exists():
                raise SystemExit(f"Local snapshot missing: {source_path}")
            clone_source = str(source_path)
        else:
            clone_source = url
        git("clone", "--quiet", "--no-hardlinks", "--no-checkout", clone_source, str(destination))
        git("-C", str(destination), "checkout", "--quiet", "--detach", commit)
        git("-C", str(destination), "remote", "set-url", "origin", url)
        actual = git("-C", str(destination), "rev-parse", "HEAD", capture=True)
        if actual != commit:
            raise SystemExit(f"Unexpected commit for {name}")
        print(f"{name}: prepared {commit[:12]}", flush=True)
    print("Sources ready. Large datasets, LFS payloads, model weights, and live dependencies are separate.")


if __name__ == "__main__":
    main()
