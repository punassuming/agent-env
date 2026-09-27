"""Versioned, extensible manifest for repository and home agent artifacts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def safe_path(root: Path, relative: str) -> Path:
    part = Path(relative)
    if not relative or part.is_absolute() or ".." in part.parts or "\\" in relative or ":" in relative:
        raise ValueError(f"Unsafe registry path: {relative}")
    candidate = root / part
    if any(p.is_symlink() for p in (candidate, *list(candidate.parents)[:len(part.parts)])):
        raise ValueError(f"Symlink in registry path: {relative}")
    return candidate


def load(source: Path) -> dict:
    data = json.loads((source / ".agents/registry.json").read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not all(isinstance(data.get(kind), dict) for kind in ("skills", "agents")):
        raise ValueError("Unsupported or invalid agent registry schema")
    for kind in ("skills", "agents"):
        for name, entry in data[kind].items():
            if not isinstance(entry, dict) or not isinstance(entry.get("destinations"), list) or not entry["destinations"]:
                raise ValueError(f"Invalid registry entry: {name}")
            safe_path(source, entry["source"])
            for destination in entry["destinations"]:
                safe_path(source, destination)
    registered = {entry["source"] for kind in ("skills", "agents") for entry in data[kind].values()}
    skills = source / ".agents/skills"
    if skills.is_dir():
        for folder in sorted(skills.iterdir()):
            relative = folder.relative_to(source).as_posix()
            if folder.is_symlink():
                raise ValueError(f"Symlink in skills registry: {folder}")
            if not folder.is_dir() or not (folder / "SKILL.md").is_file() or relative in registered:
                continue
            data["skills"].setdefault(folder.name, {"source": relative, "version": "local",
                "destinations": [f".agents/skills/{folder.name}"], "default": True})
    agents = source / ".agents/agents"
    if agents.is_dir():
        for provider in sorted(agents.iterdir()):
            if provider.is_symlink():
                raise ValueError(f"Symlink in agents registry: {provider}")
            if not provider.is_dir():
                continue
            base = {"claude": ".claude/agents", "copilot": ".github/agents"}.get(
                provider.name, f".agents/agents/{provider.name}")
            for item in sorted(provider.rglob("*.md")):
                relative = item.relative_to(source).as_posix()
                if item.is_symlink():
                    raise ValueError(f"Symlink in agents registry: {item}")
                if relative in registered:
                    continue
                name = f"{provider.name}-{item.stem}"
                target = f"{base}/{item.relative_to(provider).as_posix()}"
                data["agents"].setdefault(name, {"source": relative, "version": "local",
                    "destinations": [target], "default": True})
    return data


def files(source: Path, destination: Path, registry: dict, *, selected: set[str] | None = None) -> dict[Path, tuple[bytes, str]]:
    result = {}
    for kind in ("skills", "agents"):
        for name, entry in registry[kind].items():
            if selected is None and not entry.get("default", False) or selected is not None and name not in selected:
                continue
            origin = safe_path(source, entry["source"])
            if origin.is_dir():
                contents = (p for p in origin.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc")
            elif origin.is_file():
                contents = (origin,)
            else:
                raise ValueError(f"Missing registry source: {origin}")
            contents = list(contents)
            for dest in entry["destinations"]:
                target = safe_path(destination, dest)
                for item in contents:
                    if item.is_symlink():
                        raise ValueError(f"Symlink in registry source: {item}")
                    relative = item.relative_to(origin) if origin.is_dir() else Path()
                    output = target / relative if origin.is_dir() else target
                    if output in result and result[output][0] != item.read_bytes():
                        raise ValueError(f"Conflicting registry destinations: {output}")
                    result[output] = (item.read_bytes(), name)
    return result


def deploy(source: Path, destination: Path, *, selected: set[str] | None = None, write: bool = False) -> dict:
    source, destination = source.resolve(), destination.resolve()
    registry = load(source)
    known = set(registry["skills"]) | set(registry["agents"])
    if selected is not None and selected - known:
        raise ValueError(f"Unknown registry items: {', '.join(sorted(selected - known))}")
    receipt = destination / ".agents" / "registry-deployment.json"
    prior = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {"schema_version": 1, "files": {}}
    if prior.get("schema_version") != 1:
        raise ValueError("Unsupported deployment receipt schema")
    proposed = files(source, destination, registry, selected=selected)
    # Retain the manifest and canonical agent sources so the target can use
    # its bundled registry manager without access to this source checkout.
    manifest_source = source / ".agents/registry.json"
    proposed[destination / ".agents/registry.json"] = (manifest_source.read_bytes(), "registry")
    for entry in registry["agents"].values():
        if selected is not None and entry["source"] not in {registry["agents"][name]["source"] for name in selected if name in registry["agents"]}:
            continue
        origin = safe_path(source, entry["source"])
        if entry["source"].startswith(".agents/agents/") and origin.is_file():
            proposed[destination / entry["source"]] = (origin.read_bytes(), "registry")
    changes, conflicts = [], []
    for target, (data, _) in proposed.items():
        safe_path(destination, str(target.relative_to(destination)))
        before = hashlib.sha256(target.read_bytes()).hexdigest() if target.is_file() and not target.is_symlink() else None
        after = hashlib.sha256(data).hexdigest()
        if target.exists() and before is None or before is not None and before != after and prior["files"].get(str(target.relative_to(destination)), {}).get("sha256") != before:
            conflicts.append(str(target.relative_to(destination)))
        elif before != after:
            changes.append(str(target.relative_to(destination)))
    report = {"changes": changes, "conflicts": conflicts, "selected": sorted({name for _, name in proposed.values() if name != "registry"}), "write": write}
    if not write or conflicts:
        return report
    for target, (data, _) in proposed.items():
        if str(target.relative_to(destination)) in changes:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            if target.name.endswith(".sh"):
                target.chmod(target.stat().st_mode | 0o111)
    previous_files = prior["files"]
    for target, (data, name) in proposed.items():
        previous_files[str(target.relative_to(destination))] = {"sha256": hashlib.sha256(data).hexdigest(), "item": name}
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"schema_version": 1, "files": previous_files}, indent=2) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plan or deploy registered skills and agents")
    parser.add_argument("action", choices=("plan", "install"))
    parser.add_argument("target", type=Path)
    parser.add_argument("--select", action="append")
    args = parser.parse_args(argv)
    skill_source = Path(__file__).resolve().parents[4]
    try:
        result = deploy(skill_source, args.target, selected=set(args.select) if args.select else None,
                        write=args.action == "install")
        print(json.dumps(result, indent=2))
        return 2 if result["conflicts"] else 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"agent-env registry: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
