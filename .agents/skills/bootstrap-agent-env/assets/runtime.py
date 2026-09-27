"""Repository-owned, standard-library command runner. Copied into target .agents/bin/."""
from __future__ import annotations

import argparse
import codecs
from datetime import datetime, timezone
import fnmatch
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid


def root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_registry(base: Path) -> dict:
    path = base / ".agents" / "commands.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1 or not isinstance(registry.get("components"), dict):
        raise ValueError("Unsupported commands.json schema")
    return registry


def environment(base: Path, configured: dict, component: dict | None = None,
                command: str | None = None, *, create: bool = True) -> tuple[dict[str, str], dict[str, str]]:
    env = os.environ.copy()
    local = (base / configured.get("local_root", ".local")).resolve()
    if not local.is_relative_to(base.resolve()) or local == base.resolve():
        raise ValueError("local_root must be a directory inside the repository")
    cache = local / "cache"
    # Only set overrides for detected, selected tools. Do not redirect HOME.
    locations = {
        "uv": ("UV_CACHE_DIR", "uv"),
        "go": ("GOCACHE", "go-build"),
        "rust": ("CARGO_TARGET_DIR", "cargo-target"),
        "npm": ("npm_config_cache", "npm"),
    }
    selected = [component] if component is not None else configured["components"].values()
    enabled_tools = {tool for item in selected for tool in item.get("tools", [])}
    overrides = {}
    for tool in enabled_tools & locations.keys():
        key, folder = locations[tool]
        if key not in env:
            dest = cache / folder
            if create:
                dest.mkdir(parents=True, exist_ok=True)
            env[key] = str(dest)
            overrides[key] = str(dest)
    if component is not None and command is not None:
        execution = command_execution(component, command)
        paths = {"repo": str(base), "component": str((base / component["path"]).resolve()),
                 "local": str(local), "cache": str(cache)}
        for key, value in execution.get("env", {}).items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or not isinstance(value, str):
                raise ValueError("Command env must map variable names to strings")
            unknown = set(re.findall(r"\{([^{}]+)\}", value)) - paths.keys()
            if unknown:
                raise ValueError(f"Unknown environment path placeholder: {', '.join(sorted(unknown))}")
            rendered = value
            for placeholder, path in paths.items():
                rendered = rendered.replace("{" + placeholder + "}", path)
            env[key] = overrides[key] = rendered
        for directory in execution.get("create_dirs", []):
            if not isinstance(directory, str):
                raise ValueError("create_dirs must contain local directory names")
            rendered = directory
            for placeholder, path in paths.items():
                rendered = rendered.replace("{" + placeholder + "}", path)
            dest = Path(rendered).resolve()
            if not dest.is_relative_to(local) or dest == local:
                raise ValueError("create_dirs must stay inside the local root")
            if create:
                dest.mkdir(parents=True, exist_ok=True)
    env["AGENT_ENV_ROOT"] = str(base)
    overrides["AGENT_ENV_ROOT"] = str(base)
    return env, overrides


def command_execution(component: dict, command: str) -> dict:
    settings = component.get("execution", {})
    if not isinstance(settings, dict):
        raise ValueError("execution must map command names to settings")
    spec = settings.get(command, {})
    if not isinstance(spec, dict) or not isinstance(spec.get("env", {}), dict) or not isinstance(spec.get("create_dirs", []), list):
        raise ValueError(f"Invalid execution settings for {command}")
    needs = spec.get("sandbox", {})
    if not isinstance(needs, dict) or any(key not in {"network", "outside_workspace", "elevation", "reason"} for key in needs):
        raise ValueError(f"Invalid sandbox needs for {command}")
    if any(not isinstance(needs.get(key, False), bool) for key in ("network", "outside_workspace", "elevation")) or not isinstance(needs.get("reason", ""), str):
        raise ValueError(f"Invalid sandbox needs for {command}")
    return spec


def selected_components(registry: dict, name: str | None, all_components: bool) -> list[tuple[str, dict]]:
    components = registry["components"]
    if name:
        if name not in components:
            raise ValueError(f"Unknown component {name!r}; choose from {', '.join(components)}")
        return [(name, components[name])]
    if len(components) == 1 or all_components:
        return list(components.items())
    raise ValueError("Specify --component NAME or --all")


def state_root(base: Path, registry: dict) -> Path:
    local = (base / registry.get("local_root", ".local")).resolve()
    if not local.is_relative_to(base.resolve()) or local == base.resolve():
        raise ValueError("local_root must be a directory inside the repository")
    path = local / "agent-env"
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError("agent-env state directory resolves outside the repository")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temp, 0o600)
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}


def failure_history(folder: Path) -> list[dict]:
    entries = read_json(folder / "failure-history.json").get("failures", [])
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]
    return []


def failure_log(base: Path, folder: Path, event: dict) -> str:
    path = event.get("log")
    if not isinstance(path, str):
        return ""
    candidate = (base / path).resolve()
    if not candidate.is_relative_to(folder.resolve()) or not candidate.is_file():
        return ""
    return candidate.read_text(encoding="utf-8", errors="replace")


def record_run(base: Path, registry: dict, component: str, command: str, argv: list[str],
               code: int, output: str, reason: str = "") -> None:
    folder = state_root(base, registry)
    logs = folder / ("failures" if code else "logs")
    if not logs.resolve().is_relative_to(folder.resolve()):
        raise ValueError("agent-env log directory resolves outside local state")
    logs.mkdir(parents=True, exist_ok=True)
    log = logs / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:10] + ".log")
    with log.open("x", encoding="utf-8", errors="replace") as stream:
        stream.write(output)
    os.chmod(log, 0o600)
    event = {"schema_version": 1, "time_utc": datetime.now(timezone.utc).isoformat(),
             "component": component, "command": command, "argv": argv, "exit_code": code,
             "log": log.relative_to(base.resolve()).as_posix(), "reason": reason}
    save_json(folder / "last-run.json", event)
    if code:
        history = failure_history(folder)
        history.append(event)
        expired, history = history[:-30], history[-30:]
        save_json(folder / "failure-history.json", {"schema_version": 1, "failures": history})
        save_json(folder / "last-failure.json", event)
        for old in expired:
            old_path = (base / old.get("log", "")).resolve()
            if old_path.is_relative_to(logs.resolve()) and old_path != log:
                old_path.unlink(missing_ok=True)
    else:
        previous_failure = read_json(folder / "last-failure.json")
        if (previous_failure.get("component"), previous_failure.get("command")) == (component, command):
            previous_failure["resolved_at_utc"] = event["time_utc"]
            save_json(folder / "last-failure.json", previous_failure)
            history = failure_history(folder)
            for entry in history:
                if entry.get("log") == previous_failure.get("log"):
                    entry["resolved_at_utc"] = event["time_utc"]
                    save_json(folder / "failure-history.json", {"schema_version": 1, "failures": history})
                    break
        for previous in sorted(logs.glob("*.log"), key=lambda p: p.stat().st_mtime_ns)[:-30]:
            previous.unlink(missing_ok=True)


def command_parameters(component: dict, command: str, supplied: dict[str, str]) -> dict[str, str]:
    declared = component.get("parameters", {}).get(command, {})
    if not isinstance(declared, dict):
        raise ValueError("parameters must be a mapping")
    if set(supplied) - set(declared):
        raise ValueError(f"Unsupported parameters for {command}: {', '.join(sorted(set(supplied) - set(declared)))}")
    return declared


def expand_step(step: dict, component: dict, command: str, supplied: dict[str, str], workdir: Path) -> list[str]:
    declared = command_parameters(component, command, supplied)
    raw = step.get("argv_windows") if os.name == "nt" and step.get("argv_windows") else step.get("argv")
    if not isinstance(raw, list) or not raw or not all(isinstance(part, str) for part in raw):
        raise ValueError("Command step needs a nonempty argv list")
    rendered = []
    used = set()
    for part in raw:
        match = re.fullmatch(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", part)
        if not match:
            if any(re.search(r"\{" + re.escape(key) + r"\}", part) for key in declared):
                raise ValueError("Parameters must occupy a complete argv element")
            rendered.append(part)
            continue
        key = match.group(1)
        if key not in declared or key not in supplied:
            raise ValueError(f"Missing declared parameter: {key}")
        value = supplied[key]
        if not value or value.startswith("-") or any(x in value for x in ("\n", "\r", "\0")):
            raise ValueError(f"Invalid parameter: {key}")
        kind = declared[key].get("type") if isinstance(declared[key], dict) else None
        if kind in ("file", "nodeid"):
            path = value.split("::", 1)[0] if kind == "nodeid" else value
            candidate = (workdir / path).resolve()
            if not candidate.is_relative_to(workdir) or not candidate.is_file():
                raise ValueError(f"Parameter {key} must refer to an existing component file")
        elif kind != "text":
            raise ValueError(f"Unknown parameter type: {kind}")
        rendered.append(value)
        used.add(key)
    if set(supplied) - used:
        raise ValueError(f"Unused parameters: {', '.join(sorted(set(supplied) - used))}")
    return rendered


def input_snapshot(base: Path, registry: dict, component: dict, command: str) -> dict | None:
    spec = component.get("change_detection", {}).get(command)
    if not isinstance(spec, dict) or not isinstance(spec.get("inputs"), list) or not spec["inputs"]:
        return None
    excluded = spec.get("exclude", [])
    if not isinstance(excluded, list) or not all(isinstance(x, str) for x in excluded):
        raise ValueError("change_detection exclude must be a list of patterns")
    def excluded_path(relative: str) -> bool:
        return any(fnmatch.fnmatch(relative, rule) or fnmatch.fnmatch("./" + relative, rule)
                   for rule in excluded)

    files = set()
    local_root = (base / registry.get("local_root", ".local")).resolve()
    # For the broad default scope, Git supplies tracked and non-ignored untracked
    # paths without traversing caches or reading file contents. In a non-Git
    # workspace the existing filesystem scan below remains the fallback.
    git_listing_used = False
    if spec["inputs"] == ["**/*"] and (base / ".git").exists():
        try:
            listing = subprocess.run(["git", "-C", str(base), "ls-files", "--cached", "--others",
                                      "--exclude-standard", "-z"], capture_output=True, check=False)
            if listing.returncode == 0:
                files.update(base / os.fsdecode(name) for name in listing.stdout.split(b"\0") if name)
                git_listing_used = True
        except OSError:
            pass
    for pattern in spec["inputs"]:
        if not isinstance(pattern, str) or not pattern or Path(pattern).is_absolute() or ".." in Path(pattern).parts:
            raise ValueError("change_detection inputs must be relative repository paths")
        if git_listing_used:
            continue
        # Recursive directory inputs are the standard default; prune ignored build/cache
        # trees before descending instead of globbing through node_modules or .git.
        directory_name = "." if pattern == "**/*" else pattern[:-5] if pattern.endswith("/**/*") else None
        if directory_name is not None and not glob.has_magic(directory_name):
            directory = base / directory_name
            if directory.is_dir():
                for parent, dirs, names in os.walk(directory, followlinks=False):
                    files.update(Path(parent) / name for name in dirs if (Path(parent) / name).is_symlink())
                    dirs[:] = [name for name in dirs if name not in {".git", ".hg", ".svn"}
                               and not (Path(parent) / name).resolve().is_relative_to(local_root)
                               and not excluded_path((Path(parent) / name).relative_to(base).as_posix() + "/x")]
                    files.update(Path(parent) / name for name in names)
                continue
        for name in glob.glob(str(base / pattern), recursive=True, include_hidden=True):
            candidate = Path(name)
            if candidate.is_dir() and not candidate.is_symlink():
                files.update(p for p in candidate.rglob("*") if p.is_file() or p.is_symlink())
            elif candidate.is_file() or candidate.is_symlink():
                files.add(candidate)
    stats = {}
    for file in files:
        relative = file.relative_to(base).as_posix()
        if file.is_relative_to(local_root) or ".git" in file.relative_to(base).parts or excluded_path(relative):
            continue
        if file.is_symlink() or not file.resolve().is_relative_to(base) or not file.is_file():
            return None
        stat = file.stat()
        stats[relative] = [stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]
    if not stats:
        return None
    files = dict(sorted(stats.items()))
    return {"files": files,
            "metadata_sha256": hashlib.sha256(json.dumps(files, separators=(",", ":")).encode()).hexdigest(),
            "registry_sha256": hashlib.sha256((base / ".agents/commands.json").read_bytes()).hexdigest(),
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}


def change_state(base: Path, registry: dict, component_name: str, command: str,
                 snapshot: dict | None, update: bool = False, invalidate: bool = False) -> bool:
    if snapshot is None:
        return False
    path = state_root(base, registry) / "change-state.json"
    state = read_json(path)
    key = json.dumps([component_name, command])
    entry = state.get(key, {})
    unchanged = isinstance(entry, dict) and entry.get("snapshot") == snapshot
    if invalidate:
        state.pop(key, None)
        save_json(path, state)
    elif update:
        state[key] = {"snapshot": snapshot, "validated_at_utc": datetime.now(timezone.utc).isoformat()}
        save_json(path, state)
    return unchanged


def run_step(base: Path, registry: dict, component: str, command: str,
             argv: list[str], workdir: Path, env: dict[str, str]) -> int:
    print(f"[{component}:{command}] {' '.join(argv)}", flush=True)
    output = bytearray()
    total = 0
    try:
        launcher = [shutil.which(argv[0]) or argv[0], *argv[1:]] if os.name == "nt" else argv
        with subprocess.Popen(launcher, cwd=workdir, env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) as process:
            assert process.stdout is not None
            decoder = codecs.getincrementaldecoder("utf-8")("replace")
            for chunk in iter(lambda: process.stdout.read1(8192), b""):
                total += len(chunk)
                output.extend(chunk)
                if len(output) > 524288:
                    del output[:-524288]
                sys.stdout.write(decoder.decode(chunk))
                sys.stdout.flush()
            sys.stdout.write(decoder.decode(b"", final=True))
            code = process.wait()
    except FileNotFoundError:
        code = 127
        output = bytearray(f"MISSING EXECUTABLE {argv[0]}\n".encode())
        print(output.decode(), file=sys.stderr, end="")
    except OSError as exc:
        code = 126
        output = bytearray(f"COULD NOT EXECUTE {argv[0]}: {exc}\n".encode())
        print(output.decode(errors="replace"), file=sys.stderr, end="")
    detail = output.decode("utf-8", errors="replace")
    if total > 524288:
        detail = f"[truncated to last 512 KiB of {total} output bytes]\n" + detail
    record_run(base, registry, component, command, argv, code, detail)
    if code:
        print(f"FAILED {component}:{command}: exit {code}", file=sys.stderr)
    return code


def run_command(base: Path, registry: dict, command: str, name: str | None, all_components: bool,
                *, force: bool = False, force_components: list[str] | None = None,
                parameters: dict[str, str] | None = None) -> int:
    entries = selected_components(registry, name, all_components)
    forced = set(force_components or [])
    unknown = forced - {entry[0] for entry in entries}
    if unknown:
        raise ValueError(f"Forced component not selected: {', '.join(sorted(unknown))}")
    status = 0
    bootstrapped: set[str] = set()
    supplied = parameters or {}
    if supplied and len(entries) != 1:
        raise ValueError("Parameterized commands require --component NAME")
    incremental = command in {"validate", "lint", "format-check", "typecheck", "test", "build", "docs-check"}
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
            record_run(base, registry, component_name, command, [], 2, "", "unconfigured")
            status = status or 2
            continue
        workdir = (base / work_component["path"]).resolve()
        if not workdir.is_dir():
            print(f"MISSING DIRECTORY {component_name}: {workdir}", file=sys.stderr)
            record_run(base, registry, component_name, command, [], 2, "", "missing directory")
            status = status or 2
            continue
        snapshot = input_snapshot(base, registry, component, command)
        if incremental and not force and component_name not in forced and not supplied and snapshot is not None and not os.environ.get("CI") and not os.environ.get("GITHUB_ACTIONS") and change_state(base, registry, component_name, command, snapshot):
            print(f"SKIPPED UNCHANGED {component_name}:{command} (prior successful local run)")
            continue
        env, _ = environment(base, registry, work_component, command)
        for step in steps:
            try:
                argv = expand_step(step, component, command, supplied, workdir)
            except ValueError as exc:
                print(f"INVALID COMMAND {component_name}:{command}: {exc}", file=sys.stderr)
                record_run(base, registry, component_name, command, [], 2, "", str(exc))
                status = status or 2
                break
            code = run_step(base, registry, component_name, command, argv, workdir, env)
            if code:
                if snapshot is not None:
                    change_state(base, registry, component_name, command, snapshot, invalidate=True)
                status = status or code
                break
        else:
            if incremental and not supplied and snapshot is not None:
                after = input_snapshot(base, registry, component, command)
                if after == snapshot:
                    change_state(base, registry, component_name, command, snapshot, update=True)
                else:
                    change_state(base, registry, component_name, command, snapshot, invalidate=True)
                    print(f"INPUTS CHANGED DURING {component_name}:{command}; rerun before using a cached result",
                          file=sys.stderr)
            if command == "bootstrap":
                bootstrapped.add(component_name if work_component is component else component["bootstrap_from"])
    return status


def jsonc(text: str) -> dict:
    """Parse VS Code JSONC comments and trailing commas without changing strings."""
    out = []
    quoted = False
    escape = False
    index = 0
    while index < len(text):
        char = text[index]
        following = text[index + 1] if index + 1 < len(text) else ""
        if quoted:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                quoted = False
            index += 1
            continue
        if char == '"':
            quoted = True
        if char == "/" and following == "/":
            index += 2
            while index < len(text) and text[index] not in "\r\n":
                index += 1
            continue
        if char == "/" and following == "*":
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("Unclosed tasks.json comment")
            index = end + 2
            continue
        out.append(char)
        index += 1
    without_comments = "".join(out)
    out = []
    quoted = escape = False
    for index, char in enumerate(without_comments):
        if quoted:
            out.append(char)
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                quoted = False
            continue
        if char == '"':
            quoted = True
        if char == "," and without_comments[index + 1:].lstrip().startswith(("}", "]")):
            continue
        out.append(char)
    parsed = json.loads("".join(out))
    if not isinstance(parsed, dict) or not isinstance(parsed.get("tasks", []), list):
        raise ValueError("tasks.json needs a tasks array")
    return parsed


def task_index(base: Path) -> list[dict]:
    config = base / ".vscode/tasks.json"
    if not config.is_file():
        return []
    data = jsonc(config.read_text(encoding="utf-8"))
    platform = "windows" if os.name == "nt" else "osx" if sys.platform == "darwin" else "linux"
    indexed = []
    for item in data.get("tasks", []):
        if not isinstance(item, dict):
            continue
        merged = dict(item)
        merged.update(item.get(platform, {}) if isinstance(item.get(platform), dict) else {})
        label = merged.get("label")
        if not isinstance(label, str) or not label:
            continue
        reason = None
        if merged.get("type") != "process":
            reason = "Only VS Code process tasks are executable without shell interpretation"
        if merged.get("dependsOn") or merged.get("isBackground") or merged.get("runOptions"):
            reason = "Task dependencies, background mode and run options need project-specific adaptation"
        command, args = merged.get("command"), merged.get("args", [])
        if not isinstance(command, str) or not isinstance(args, list) or not all(isinstance(x, str) for x in args):
            reason = "Task command and args must be literal strings"
            command, args = "", []
        options = merged.get("options", {})
        if not isinstance(options, dict) or not isinstance(options.get("env", {}), dict):
            reason = "Task options must be literal mappings"
            options = {}
        if any(not isinstance(k, str) or not isinstance(v, str)
               for k, v in options.get("env", {}).items()):
            reason = "Task environment keys and values must be literal strings"
        cwd = options.get("cwd", "${workspaceFolder}")
        if not isinstance(cwd, str):
            reason = "Task cwd must be a literal directory"
            cwd = ""
        variables = re.compile(r"\$\{[^}]+\}")
        if any(variables.search(x) for x in [command, *args]) or any(
                variables.search(str(v)) or not isinstance(v, str) for v in options.get("env", {}).values()):
            reason = "Dynamic VS Code variables need explicit project adaptation"
        candidate = cwd.replace("${workspaceFolder}", str(base))
        directory = Path(candidate)
        if not directory.is_absolute():
            directory = base / directory
        if variables.search(candidate) or not directory.resolve().is_relative_to(base.resolve()) or not directory.is_dir():
            reason = "Task working directory must exist inside the repository"
        indexed.append({"label": label, "source": ".vscode/tasks.json", "type": merged.get("type"),
                        "argv": [command, *args], "cwd": cwd, "env": options.get("env", {}),
                        "runnable": reason is None, "reason": reason})
    return indexed


def catalog(base: Path, registry: dict) -> dict:
    return {"registry": [{"component": name, "path": item.get("path"),
                          "commands": item.get("commands", {}),
                          "descriptions": item.get("descriptions", {}),
                          "execution": item.get("execution", {}),
                          "parameters": item.get("parameters", {}),
                          "change_detection": sorted(item.get("change_detection", {}))}
                         for name, item in registry["components"].items()],
            "vscode_tasks": task_index(base)}


def run_task(base: Path, registry: dict, label: str) -> int:
    matches = [task for task in task_index(base) if task["label"] == label]
    if len(matches) != 1:
        raise ValueError(f"Expected one VS Code task labeled {label!r}; found {len(matches)}")
    task = matches[0]
    if not task["runnable"]:
        raise ValueError(f"Task {label!r} is not directly runnable: {task['reason']}")
    cwd = Path(task["cwd"].replace("${workspaceFolder}", str(base)))
    if not cwd.is_absolute():
        cwd = base / cwd
    cwd = cwd.resolve()
    env, _ = environment(base, registry)
    env.update(task["env"])
    return run_step(base, registry, "vscode", label, task["argv"], cwd, env)


def latest_status(base: Path, registry: dict) -> dict:
    folder = state_root(base, registry)
    last, failure = read_json(folder / "last-run.json"), read_json(folder / "last-failure.json")
    resolved = bool(failure.get("resolved_at_utc"))
    return {"last_run": last or None, "last_failure": failure or None,
            "last_failure_followed_by_success": resolved}


def failures(base: Path, registry: dict, component: str | None, limit: int, as_json: bool) -> None:
    if not 1 <= limit <= 30:
        raise ValueError("--limit must be between 1 and 30")
    folder = state_root(base, registry)
    history = failure_history(folder)
    if not history:
        last = read_json(folder / "last-failure.json")
        history = [last] if last else []  # Older installations have only this receipt.
    entries = [entry for entry in reversed(history) if component is None or entry.get("component") == component][:limit]
    results = [{"event": entry, "output": failure_log(base, folder, entry)} for entry in entries]
    if as_json:
        print(json.dumps({"failures": results}, indent=2))
    elif not results:
        print("No recorded failures")
    else:
        for result in results:
            event = result["event"]
            print(f"FAILED {event.get('component')}:{event.get('command')} exit {event.get('exit_code')} at {event.get('time_utc')}")
            if event.get("reason"):
                print(f"Reason: {event['reason']}")
            print(result["output"] or "[No retained output]", end="\n")


def parse_parameters(items: list[str], file: str | None, node_id: str | None) -> dict[str, str]:
    values = {}
    for entry in items:
        key, separator, value = entry.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key) or key in values:
            raise ValueError("--param requires a distinct NAME=VALUE")
        values[key] = value
    for key, value in (("file", file), ("node_id", node_id)):
        if value is not None:
            if key in values:
                raise ValueError(f"Duplicate parameter {key}")
            values[key] = value
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run repository-defined agent commands")
    parser.add_argument("command", nargs="?", default="help", help="help, list, doctor, or a registered command")
    parser.add_argument("--component", help="Component name")
    parser.add_argument("--all", action="store_true", help="Run every component")
    parser.add_argument("--json", action="store_true", help="Machine-readable list or doctor output")
    parser.add_argument("--force", action="store_true", help="Run selected components even if their validated inputs are unchanged")
    parser.add_argument("--force-component", action="append", default=[], help="With --all, always run this component (repeatable)")
    parser.add_argument("--changed", action="store_true", help="Legacy alias for default incremental validation behavior")
    parser.add_argument("--limit", type=int, default=1, help="Number of recent failures to display (1-30)")
    parser.add_argument("--param", action="append", default=[], help="Named parameter for a registered command: NAME=VALUE")
    parser.add_argument("--file", help="Shorthand for --param file=PATH")
    parser.add_argument("--node-id", help="Shorthand for --param node_id=FILE::TEST")
    parser.add_argument("--task", help="VS Code process task label for run-task")
    parser.add_argument("--for-command", default="validate", help="Command to inspect with changes")
    args = parser.parse_args(argv)
    base = root()
    try:
        registry = load_registry(base)
        if args.command in ("catalog", "tasks"):
            data = catalog(base, registry)
            print(json.dumps(data, indent=2) if args.json else "\n".join(
                [f"{entry['component']} ({entry['path']}): {', '.join(entry['commands'])}" for entry in data["registry"]] +
                [f"VS Code {task['label']}: {'runnable' if task['runnable'] else task['reason']}" for task in data["vscode_tasks"]]))
            return 0
        if args.command == "lookup":
            entries = selected_components(registry, args.component, args.all)
            report = {}
            for name, component in entries:
                target = args.for_command
                steps = component.get("commands", {}).get(target)
                spec = command_execution(component, target)
                _, overrides = environment(base, registry, component, target, create=False)
                report[name] = {"command": target, "configured": bool(steps),
                                "description": component.get("descriptions", {}).get(target, ""),
                                "cwd": str((base / component["path"]).resolve()),
                                "steps": steps or [], "parameters": component.get("parameters", {}).get(target, {}),
                                "environment_overrides": overrides, "create_dirs": spec.get("create_dirs", []),
                                "sandbox_needs": spec.get("sandbox", {}),
                                "change_detection": component.get("change_detection", {}).get(target)}
            print(json.dumps(report, indent=2))
            return 0
        if args.command == "run-task":
            if not args.task:
                raise ValueError("run-task requires --task LABEL")
            return run_task(base, registry, args.task)
        if args.command == "status":
            print(json.dumps(latest_status(base, registry), indent=2))
            return 0
        if args.command == "failures":
            failures(base, registry, args.component, args.limit, args.json)
            return 0
        if args.command == "changes":
            report = {}
            for name, component in selected_components(registry, args.component, args.all):
                snapshot = input_snapshot(base, registry, component, args.for_command)
                previous = read_json(state_root(base, registry) / "change-state.json").get(json.dumps([name, args.for_command]), {})
                if not isinstance(previous, dict):
                    previous = {}
                old = previous.get("snapshot", {}).get("files", {}) if isinstance(previous, dict) else {}
                new = snapshot["files"] if snapshot else {}
                changed_files = sorted(file for file in old.keys() | new.keys() if old.get(file) != new.get(file))
                newest = max(x[1] for x in new.values()) / 1e9 if new else None
                report[name] = {"configured": snapshot is not None,
                                "unchanged_since_success": bool(snapshot and previous.get("snapshot") == snapshot),
                                "metadata_sha256": snapshot.get("metadata_sha256") if snapshot else None,
                                "files": len(new), "changed_files": changed_files,
                                "registry_or_runner_changed": bool(snapshot and previous.get("snapshot") and any(
                                    snapshot.get(key) != previous["snapshot"].get(key)
                                    for key in ("registry_sha256", "runner_sha256"))),
                                "last_success_utc": previous.get("validated_at_utc"),
                                "newest_input_time_utc": datetime.fromtimestamp(newest, timezone.utc).isoformat() if newest else None,
                                "newest_input_age_seconds": max(0, int(datetime.now(timezone.utc).timestamp() - newest)) if newest else None}
            print(json.dumps(report, indent=2))
            return 0
        if args.command in ("help", "list"):
            if args.json:
                print(json.dumps(registry, indent=2))
            else:
                for name, component in registry["components"].items():
                    print(f"{name} ({component['path']}): {', '.join(component.get('commands', {}))}")
                print("Use lookup --component NAME --for-command COMMAND to inspect a run. Use --force to rerun; failures shows logs. Unconfigured commands fail.")
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
        return run_command(base, registry, args.command, args.component, args.all,
                           force=args.force, force_components=args.force_component,
                           parameters=parse_parameters(args.param, args.file, args.node_id))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"agent-env: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
