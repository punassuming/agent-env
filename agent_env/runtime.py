"""Repository-owned, standard-library command runner. Copied into target .agents/bin/."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_registry(base: Path) -> dict:
    path = base / ".agents" / "commands.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1 or not isinstance(registry.get("components"), dict):
        raise ValueError("Unsupported commands.json schema")
    return registry


def environment(base: Path, configured: dict) -> dict[str, str]:
    env = os.environ.copy()
    cache = base / configured.get("local_root", ".local") / "cache"
    # Only set overrides for detected, selected tools. Do not redirect HOME.
    locations = {
        "uv": ("UV_CACHE_DIR", "uv"),
        "go": ("GOCACHE", "go-build"),
        "rust": ("CARGO_TARGET_DIR", "cargo-target"),
        "npm": ("npm_config_cache", "npm"),
    }
    tools = {tool for component in configured["components"].values() for tool in component.get("tools", [])}
    for tool in tools & locations.keys():
        key, folder = locations[tool]
        if key not in env:
            dest = cache / folder
            dest.mkdir(parents=True, exist_ok=True)
            env[key] = str(dest)
    env["AGENT_ENV_ROOT"] = str(base)
    return env


def selected_components(registry: dict, name: str | None, all_components: bool) -> list[tuple[str, dict]]:
    components = registry["components"]
    if name:
        if name not in components:
            raise ValueError(f"Unknown component {name!r}; choose from {', '.join(components)}")
        return [(name, components[name])]
    if len(components) == 1 or all_components:
        return list(components.items())
    raise ValueError("Specify --component NAME or --all")


def run_command(base: Path, registry: dict, command: str, name: str | None, all_components: bool) -> int:
    entries = selected_components(registry, name, all_components)
    env = environment(base, registry)
    status = 0
    bootstrapped: set[str] = set()
    for component_name, component in entries:
        steps = component.get("commands", {}).get(command)
        work_component = component
        if command == "bootstrap" and not steps and component.get("bootstrap_from"):
            inherited = component["bootstrap_from"]
            if inherited in bootstrapped:
                print(f"[{component_name}:bootstrap] already installed through {inherited}")
                continue
            work_component = registry["components"].get(inherited, {})
            steps = work_component.get("commands", {}).get(command)
        if command == "bootstrap" and steps and work_component is component and component_name in bootstrapped:
            continue
        if not steps:
            print(f"UNCONFIGURED {component_name}:{command}", file=sys.stderr)
            status = status or 2
            continue
        workdir = (base / work_component["path"]).resolve()
        if not workdir.is_dir():
            print(f"MISSING DIRECTORY {component_name}: {workdir}", file=sys.stderr)
            status = status or 2
            continue
        for step in steps:
            argv = step.get("argv_windows") if os.name == "nt" and step.get("argv_windows") else step.get("argv")
            if not isinstance(argv, list) or not argv or not all(isinstance(v, str) for v in argv):
                print(f"INVALID COMMAND {component_name}:{command}", file=sys.stderr)
                status = status or 2
                break
            print(f"[{component_name}:{command}] {' '.join(argv)}", flush=True)
            try:
                result = subprocess.run(argv, cwd=workdir, env=env, check=False)
            except FileNotFoundError:
                print(f"MISSING EXECUTABLE {argv[0]}", file=sys.stderr)
                status = status or 127
                break
            if result.returncode:
                print(f"FAILED {component_name}:{command}: exit {result.returncode}", file=sys.stderr)
                status = status or result.returncode
                break
        else:
            if command == "bootstrap":
                bootstrapped.add(component_name if work_component is component else component["bootstrap_from"])
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run repository-defined agent commands")
    parser.add_argument("command", nargs="?", default="help", help="help, list, doctor, or a registered command")
    parser.add_argument("--component", help="Component name")
    parser.add_argument("--all", action="store_true", help="Run every component")
    parser.add_argument("--json", action="store_true", help="Machine-readable list or doctor output")
    args = parser.parse_args(argv)
    base = root()
    try:
        registry = load_registry(base)
        if args.command in ("help", "list"):
            if args.json:
                print(json.dumps(registry, indent=2))
            else:
                for name, component in registry["components"].items():
                    print(f"{name} ({component['path']}): {', '.join(component.get('commands', {}))}")
                print("Use COMMAND --component NAME, or COMMAND --all. Unconfigured commands fail.")
            return 0
        if args.command == "doctor":
            report = {}
            for name, component in registry["components"].items():
                missing = sorted({cmd[0] for steps in component.get("commands", {}).values()
                                  for s in steps for cmd in [s.get("argv_windows") if os.name == "nt" and s.get("argv_windows") else s.get("argv")]
                                  if cmd and not (base / component["path"] / cmd[0]).exists()
                                  and shutil.which(cmd[0]) is None})
                report[name] = {"path_exists": (base / component["path"]).is_dir(), "missing_executables": missing}
            local = base / registry.get("local_root", ".local")
            report["local_writable"] = os.access(local if local.exists() else base, os.W_OK)
            if args.json:
                print(json.dumps(report, indent=2))
            else:
                print(json.dumps(report, indent=2))
            return 0 if report["local_writable"] and all(v["path_exists"] and not v["missing_executables"] for v in report.values() if isinstance(v, dict)) else 1
        return run_command(base, registry, args.command, args.component, args.all)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"agent-env: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
