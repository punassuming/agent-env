"""Conservative bootstrap: discover, propose, then merge into a target repository."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

VERSION = "0.8.0"
SKILL_ROOT = Path(__file__).resolve().parents[1]


def step(*argv: str, windows: tuple[str, ...] = ()) -> dict:
    result = {"argv": list(argv)}
    if windows:
        result["argv_windows"] = list(windows)
    return result


def merge(commands: dict, additions: dict) -> None:
    for name, steps in additions.items():
        commands.setdefault(name, []).extend(steps)


def discover(path: Path) -> dict:
    found: dict[str, dict] = {}
    candidates = [path]
    for parent in ("apps", "packages", "services", "lib"):
        folder = path / parent
        if folder.is_dir():
            candidates += [p for p in folder.iterdir() if p.is_dir() and not p.is_symlink()]
    for folder in candidates:
        relative = folder.relative_to(path).as_posix()
        commands: dict[str, list[dict]] = {}
        tools: list[str] = []
        evidence: list[str] = []
        bootstrap_from = None
        if (folder / "Cargo.toml").exists():
            evidence.append("Cargo.toml")
            tools.append("rust")
            merge(commands, {"format-check": [step("cargo", "fmt", "--all", "--", "--check")],
                             "format": [step("cargo", "fmt", "--all")],
                             "lint": [step("cargo", "clippy", "--all-targets", "--", "-D", "warnings")],
                             "test": [step("cargo", "test")], "build": [step("cargo", "build")]})
        if (folder / "go.mod").exists() or (folder / "go.work").exists():
            evidence.append("go.mod" if (folder / "go.mod").exists() else "go.work")
            tools.append("go")
            merge(commands, {"lint": [step("go", "vet", "./...")], "test": [step("go", "test", "./...")],
                             "build": [step("go", "build", "./...")]})
        if (folder / "pyproject.toml").exists():
            evidence.append("pyproject.toml")
            tools.append("python")
            uv_workspace = relative != "." and (path / "uv.lock").exists() and (path / "pyproject.toml").exists() and "[tool.uv.workspace]" in (path / "pyproject.toml").read_text(encoding="utf-8")
            if (folder / "uv.lock").exists() or uv_workspace:
                evidence.append("uv.lock" if (folder / "uv.lock").exists() else "workspace-root:uv.lock")
                tools.append("uv")
                if uv_workspace:
                    bootstrap_from = "root"
                else:
                    merge(commands, {"bootstrap": [step("uv", "sync", "--locked")]})
                if (folder / "tests").is_dir():
                    merge(commands, {"test": [step("uv", "run", "--locked", "pytest")]})
                content = (folder / "pyproject.toml").read_text(encoding="utf-8")
                if "[tool.ruff" in content or '"ruff"' in content:
                    merge(commands, {"lint": [step("uv", "run", "--locked", "ruff", "check", ".")],
                                     "format-check": [step("uv", "run", "--locked", "ruff", "format", "--check", ".")],
                                     "format": [step("uv", "run", "--locked", "ruff", "format", ".")]})
        package = folder / "package.json"
        if package.exists():
            evidence.append("package.json")
            tools.append("node")
            data = json.loads(package.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {})
            manager = "pnpm" if (folder / "pnpm-lock.yaml").exists() or (path / "pnpm-lock.yaml").exists() else "npm"
            tools.append(manager)
            lock = "pnpm-lock.yaml" if manager == "pnpm" else "package-lock.json"
            if (folder / lock).exists():
                evidence.append(lock)
                merge(commands, {"bootstrap": [step(manager, "install", "--frozen-lockfile") if manager == "pnpm" else step("npm", "ci")]})
            elif relative != "." and (path / lock).exists() and (path / "package.json").exists():
                evidence.append("workspace-root:" + lock)
                bootstrap_from = "root"
            for canonical, names in {"test": ("test",), "lint": ("lint",), "typecheck": ("typecheck", "type-check"),
                                     "build": ("build",), "format": ("format",),
                                     "format-check": ("format:check", "format-check"),
                                     "docs-check": ("docs:check", "docs-check")}.items():
                match = next((n for n in names if n in scripts and scripts[n] not in ("echo \"Error: no test specified\" && exit 1",)), None)
                if match:
                    merge(commands, {canonical: [step(manager, "run", match)]})
        if (folder / "gradlew").exists() or (folder / "gradlew.bat").exists():
            evidence.append("gradlew")
            tools.append("gradle")
            gradle_check = step("./gradlew", "check", windows=("gradlew.bat", "check"))
            merge(commands, {"test": [step("./gradlew", "test", windows=("gradlew.bat", "test"))],
                             "build": [step("./gradlew", "build", windows=("gradlew.bat", "build"))]})
            if (folder / "app" / "build.gradle.kts").exists() or (folder / "app" / "build.gradle").exists():
                tools.append("android")
                # Android test and build tasks depend on modules and variants: leave candidate selection to agent.
                commands["test"] = [s for s in commands["test"] if s["argv"][0] != "./gradlew"]
        if not evidence:
            continue
        checks = [name for name in ("format-check", "lint", "typecheck", "test", "build", "docs-check") if name in commands]
        commands["validate"] = [s for name in checks for s in commands[name] if not ("gradle" in tools and s["argv"][0] == "./gradlew")]
        if "gradle" in tools:
            commands["validate"].append(gradle_check)
        found["root" if relative == "." else relative.replace("/", "-")] = {
            "path": relative, "evidence": evidence, "tools": sorted(set(tools)), "commands": commands,
            "unconfigured": [name for name in ("test", "debug", "deploy-plan", "deploy", "verify-deploy") if not commands.get(name)]
        }
        if bootstrap_from:
            found["root" if relative == "." else relative.replace("/", "-")]["bootstrap_from"] = bootstrap_from
    return found


def tracked_local(path: Path) -> bool:
    result = subprocess.run(["git", "-C", str(path), "ls-files", "--", ".local"], capture_output=True, text=True, check=False)
    return bool(result.stdout.strip())


def install(path: Path, found: dict) -> list[str]:
    source_repository = SKILL_ROOT.parents[2]
    deployed = []
    if (source_repository / ".agents/registry.json").is_file():
        from importlib.util import module_from_spec, spec_from_file_location
        registry_file = SKILL_ROOT / "scripts" / "registry.py"
        spec = spec_from_file_location("bootstrap_skill_registry", registry_file)
        module = module_from_spec(spec)
        spec.loader.exec_module(module)
        plan = module.deploy(source_repository, path)
        if plan["conflicts"]:
            raise ValueError("Registry conflicts: " + ", ".join(plan["conflicts"]))
        deployed = module.deploy(source_repository, path, write=True)["selected"]
    agent = path / ".agents"
    agent.mkdir(exist_ok=True)
    manifest_path = agent / "bootstrap.json"
    previous = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    if previous.get("schema_version", 1) != 1:
        raise ValueError("Unsupported bootstrap schema; inspect and migrate manually")
    registry_path = agent / "commands.json"
    old = json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {"schema_version": 1, "components": {}}
    if old.get("schema_version") != 1:
        raise ValueError("Unsupported command registry schema")
    # Existing decisions win. Propose and add newly discovered components without replacing command edits.
    for name, detected in found.items():
        old["components"].setdefault(name, detected)
    local_root = previous.get("local_root", ".local")
    if not previous and tracked_local(path):
        local_root = ".agent-local"
    old["local_root"] = local_root
    registry_path.write_text(json.dumps(old, indent=2) + "\n", encoding="utf-8")
    previous.update({"schema_version": 1, "skill": "bootstrap-agent-env", "pending_version": VERSION,
                     "local_root": local_root,
                     "detected": {name: {"evidence": data["evidence"], "tools": data["tools"]} for name, data in found.items()}})
    manifest_path.write_text(json.dumps(previous, indent=2) + "\n", encoding="utf-8")
    actions = ["Wrote .agents/bootstrap.json", "Merged .agents/commands.json"] + ["Registered " + name for name in deployed]

    src = SKILL_ROOT / "assets" / "runtime.py"
    dest = agent / "bin" / "runtime.py"
    dest.parent.mkdir(exist_ok=True)
    receipt = agent / "runtime-deployment.json"
    previous_runtime = json.loads(receipt.read_text(encoding="utf-8")) if receipt.exists() else {}
    source_hash = hashlib.sha256(src.read_bytes()).hexdigest()
    installed_hash = hashlib.sha256(dest.read_bytes()).hexdigest() if dest.exists() else None
    if not dest.exists():
        shutil.copyfile(src, dest)
        actions.append("Added .agents/bin/runtime.py")
    elif installed_hash == previous_runtime.get("installed_sha256") and installed_hash != source_hash:
        shutil.copyfile(src, dest)
        actions.append("Updated unchanged .agents/bin/runtime.py")
    elif installed_hash != source_hash:
        actions.append("Review .agents/bin/runtime.py: local or untracked changes preserved")
    if hashlib.sha256(dest.read_bytes()).hexdigest() == source_hash:
        receipt.write_text(json.dumps({"schema_version": 1, "source_version": VERSION,
                                       "installed_sha256": source_hash}, indent=2) + "\n", encoding="utf-8")
    workflow = agent / "skills" / "repo-agent-workflow" / "SKILL.md"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    if not workflow.exists():
        shutil.copyfile(SKILL_ROOT / "assets" / "skills" / "repo-agent-workflow" / "SKILL.md", workflow)
        actions.append("Added .agents/skills/repo-agent-workflow/SKILL.md")
    claude = path / ".claude" / "skills" / "repo-agent-workflow" / "SKILL.md"
    if not claude.exists():
        claude.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SKILL_ROOT / "assets" / "skills" / "repo-agent-workflow" / "CLAUDE.md", claude)
        actions.append("Added .claude/skills/repo-agent-workflow/SKILL.md")
    examples = SKILL_ROOT / "assets" / "scripts"
    scripts = path / "scripts"
    scripts.mkdir(exist_ok=True)
    for name in ("agent-env.sh", "agent-env.ps1"):
        target = scripts / name
        if not target.exists():
            shutil.copyfile(examples / name, target)
            if name.endswith(".sh"):
                target.chmod(target.stat().st_mode | 0o111)
            actions.append(f"Added scripts/{name}")
    ignore = path / ".gitignore"
    pattern = f"/{local_root}/"
    current = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
    if pattern not in current.splitlines():
        ignore.write_text(current + ("\n" if current and not current.endswith("\n") else "") + pattern + "\n", encoding="utf-8")
        actions.append("Updated .gitignore")
    agents_md = path / "AGENTS.md"
    note = ("## Agent environment\n\nRun `scripts/agent-env.sh validate --all` on Unix or "
            "`scripts/agent-env.ps1 validate --all` in PowerShell. Use `scripts/agent-env.sh catalog --json` "
            "for registered commands and VS Code tasks, and `scripts/agent-env.sh status` for the last failure. "
            "Inspect `.agents/commands.json` for components and update its commands when the project changes. "
            f"Disposable caches and logs belong in `{local_root}/`. "
            "Deploy commands require explicit target-specific configuration.\n")
    if not agents_md.exists():
        agents_md.write_text("# Repository instructions\n\n" + note, encoding="utf-8")
        actions.append("Added AGENTS.md")
    elif "## Agent environment" not in agents_md.read_text(encoding="utf-8"):
        with agents_md.open("a", encoding="utf-8") as f:
            f.write("\n" + note)
        actions.append("Extended AGENTS.md")
    claude_md = path / "CLAUDE.md"
    if claude_md.exists() and "@AGENTS.md" not in claude_md.read_text(encoding="utf-8"):
        with claude_md.open("a", encoding="utf-8") as f:
            f.write("\n@AGENTS.md\n")
        actions.append("Imported AGENTS.md from existing CLAUDE.md")
    return actions


def finalize(path: Path) -> None:
    record = path / ".agents" / "bootstrap.json"
    if not record.exists():
        raise ValueError("No pending bootstrap installation")
    data = json.loads(record.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or data.get("pending_version") != VERSION:
        raise ValueError("Pending version does not match this installer; inspect before finalizing")
    runner = path / ".agents" / "bin" / "runtime.py"
    if not runner.exists():
        raise ValueError("Missing installed command runner")
    registry = json.loads((path / ".agents" / "commands.json").read_text(encoding="utf-8"))
    components = registry.get("components", {})
    if not components or any(not c.get("commands", {}).get("validate") for c in components.values()):
        raise ValueError("Each component needs real validate steps before finalizing")
    for command in ("doctor", "validate"):
        result = subprocess.run([sys.executable, str(runner), command, "--all"], cwd=path, check=False)
        if result.returncode:
            raise ValueError(f"{command} failed (exit {result.returncode}); applied version unchanged")
    data["applied_version"] = data.pop("pending_version")
    record.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assess or install agent environment into a repository")
    parser.add_argument("mode", choices=("assess", "install", "finalize"))
    parser.add_argument("target", type=Path)
    args = parser.parse_args(argv)
    target = args.target.resolve()
    if not target.is_dir():
        parser.error("target must be an existing directory")
    try:
        if args.mode == "finalize":
            finalize(target)
            print(f"Applied bootstrap version {VERSION}")
            return 0
        found = discover(target)
        if args.mode == "assess":
            print(json.dumps({"skill_version": VERSION, "components": found}, indent=2))
        else:
            for action in install(target, found):
                print(action)
            print("Agent review required: verify candidates, run checks, configure deploy targets and CI.")
        return 0
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"agent-env: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
