"""Create the local environment, then run offline checks. No package downloads or API calls."""

from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit("Use Python 3.11 or later; Python 3.12 is the team's default.")
    environment = ROOT / ".venv"
    executable = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not executable.exists():
        print("Creating .venv using the installed Python...", flush=True)
        venv.EnvBuilder(with_pip=True).create(environment)
    elif subprocess.run([str(executable), "-m", "pip", "--version"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
        # Recover a previously interrupted environment without deleting local files.
        subprocess.run([str(executable), "-m", "ensurepip", "--upgrade"], check=True)
    env_file = ROOT / ".env"
    if not env_file.exists():
        # Never replace an existing local configuration.
        env_file.write_text((ROOT / ".env.example").read_text(encoding="utf-8"), encoding="utf-8")
    commands = [
        [str(executable), "-m", "evirecall", "doctor"],
        [str(executable), "-m", "unittest", "discover", "-s", "tests", "-v"],
        [str(executable), "-m", "evirecall", "smoke"],
    ]
    for command in commands:
        subprocess.run(command, cwd=ROOT, check=True)
    print("Offline setup complete. Next: prepare pinned sources and implement the three work packages.")


if __name__ == "__main__":
    main()
