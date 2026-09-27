"""Coordinate explicitly listed, separately bootstrapped repositories."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description="Run a command across explicit workspace repos")
    parser.add_argument("command", choices=("doctor", "validate", "test", "build", "lint"))
    parser.add_argument("--manifest", type=Path, default=Path("workspace.json"))
    parser.add_argument("--project", action="append", help="Run selected project name(s)")
    args = parser.parse_args()
    manifest = args.manifest.resolve()
    try:
        projects = json.loads(manifest.read_text(encoding="utf-8"))["projects"]
    except (OSError, ValueError, KeyError) as exc:
        parser.error(f"Invalid workspace manifest: {exc}")
    if not isinstance(projects, dict) or not projects or any(not isinstance(k, str) or not isinstance(v, str) or not v for k, v in projects.items()):
        parser.error("Workspace manifest must have a nonempty projects mapping of names to paths")
    names = list(dict.fromkeys(args.project or projects))
    if any(name not in projects for name in names):
        parser.error("Unknown project; inspect workspace.json")
    errors = 0
    for name in names:
        repo = (manifest.parent / projects[name]).resolve()
        runner = repo / ".agents" / "bin" / "runtime.py"
        print(f"[{name}] {args.command}", flush=True)
        if not repo.is_dir():
            print(f"[{name}] missing project directory: {repo}", file=sys.stderr)
            errors += 1
            continue
        if not runner.is_file():
            print(f"[{name}] missing runner: {runner}", file=sys.stderr)
            errors += 1
            continue
        result = subprocess.run([sys.executable, str(runner), args.command, "--all"], cwd=repo, check=False)
        errors += result.returncode != 0
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
