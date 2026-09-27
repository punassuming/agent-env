"""Sync a checked-out agent-env package into a user's .agents directory."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from . import VERSION
from .registry import files, load


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tracked_files(source: Path) -> list[Path]:
    result = subprocess.run(["git", "-C", str(source), "ls-files", "-z"], capture_output=True, check=False)
    if result.returncode:
        manifest = source.parent / "agent-env-sync.json"
        if source.name != "agent-env" or not manifest.is_file():
            raise ValueError("source must be a Git checkout or a previously synced agent-env snapshot")
        recorded = json.loads(manifest.read_text(encoding="utf-8")).get("files", {})
        paths = [Path(key).relative_to(source) for key in recorded if Path(key).is_relative_to(source)]
    else:
        paths = [Path(os.fsdecode(raw)) for raw in result.stdout.split(b"\0") if raw]
    for relative in paths:
        if relative.is_absolute() or ".." in relative.parts or (source / relative).is_symlink():
            raise ValueError(f"Unsafe tracked path: {relative}")
    return paths


def proposals(source: Path, home: Path, claude: bool = False) -> dict[Path, bytes]:
    copied = {home / "agent-env" / relative: (source / relative).read_bytes()
              for relative in tracked_files(source) if (source / relative).is_file()}
    registry = load(source)
    # Home destinations expose canonical skills in ~/.agents/skills and Claude
    # adapters in ~/.claude; repository-specific Copilot definitions stay in repos.
    selected = {name for name, entry in registry["skills"].items() if entry.get("default")}
    if claude:
        selected.update(name for name, entry in registry["agents"].items()
                        if entry.get("default") and any(p.startswith(".claude/") for p in entry["destinations"]))
    for target, (data, _) in files(source, home.parent, registry, selected=selected).items():
        relative = target.relative_to(home.parent)
        if relative.parts[:2] == (".agents", "skills"):
            copied[home / Path(*relative.parts[1:])] = data
        elif claude and relative.parts[0] == ".claude":
            copied[home.parent / relative] = data
    return copied


def sync(source: Path, home: Path, claude: bool = False, write: bool = False) -> dict:
    source, home = source.resolve(), home.expanduser().resolve()
    manifest = home / "agent-env-sync.json"
    old = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {"schema_version": 1, "files": {}}
    if old.get("schema_version") != 1:
        raise ValueError("Unknown home sync schema; inspect before updating")
    desired = proposals(source, home, claude)
    changes: list[str] = []
    conflicts: list[str] = []
    for target, data in desired.items():
        key = str(target)
        target_hash = digest(data)
        if target.is_symlink():
            conflicts.append(key)
        elif target.exists():
            if not target.is_file():
                conflicts.append(key)
            elif digest(target.read_bytes()) != target_hash:
                source_checkout_file = (target.is_relative_to(home / "agent-env")
                                        and target.resolve() == (source / target.relative_to(home / "agent-env")).resolve())
                if old["files"].get(key) != digest(target.read_bytes()) and not source_checkout_file:
                    conflicts.append(key)
                else:
                    changes.append(key)
        else:
            changes.append(key)
    report = {"source_version": VERSION, "write": write, "changes": changes, "conflicts": conflicts}
    if conflicts or not write:
        return report
    for target, data in desired.items():
        if str(target) not in changes:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as file:
            file.write(data)
            staged = Path(file.name)
        staged.chmod((source / target.relative_to(home / "agent-env")).stat().st_mode & 0o777 if target.is_relative_to(home / "agent-env") else 0o644)
        staged.replace(target)
    old.update({"schema_version": 1, "source_version": VERSION,
                "source": str(source), "files": {str(p): digest(data) for p, data in desired.items()}})
    home.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(old, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or sync agent-env into ~/.agents")
    parser.add_argument("action", choices=("plan", "sync", "status"))
    parser.add_argument("--home", type=Path, default=Path.home() / ".agents", help="Destination .agents directory")
    parser.add_argument("--claude", action="store_true", help="Also install the canonical skill into ~/.claude/skills")
    args = parser.parse_args(argv)
    try:
        result = sync(Path(__file__).resolve().parents[1], args.home, args.claude, write=args.action == "sync")
        print(json.dumps(result, indent=2))
        return 2 if result["conflicts"] else 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"agent-env home: {exc}", file=sys.stderr)
        return 2
