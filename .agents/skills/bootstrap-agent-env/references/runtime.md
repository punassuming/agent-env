# Runner extensions and evidence

The installed runner is a repository-owned command adapter, not a replacement for the project's native task system. `catalog --json` lists command argv, declared parameters, descriptions, change policies and `.vscode/tasks.json` entries. `help` and `list --json` retain their original behavior. Bash and PowerShell wrappers pass the same arguments to the runner.

## Failure handoff

Every executed step writes an ignored log under `<local_root>/agent-env/logs/` and updates `last-run.json`. A failed step, missing executable, missing directory or unconfigured command updates `last-failure.json`. `status` reads both receipts, including the latest failing argv, exit code, UTC time, log path and whether a later successful run of **that component and command** followed it. The last failure is retained for diagnosis; an unrelated passing check does not erase it. Logs retain the last 512 KiB of step output and only the 30 newest files are kept. A local log can contain sensitive command output; keep the local root ignored, restrict access, and do not commit or upload it without review. This is a handoff artifact, not an issue tracker or an assertion that the command was rerun in CI.

```bash
scripts/agent-env.sh status
scripts/agent-env.sh catalog --json
```

When debugging, read `status` and the referenced log before rerunning a failed step; verify the file still exists because logs rotate. The assessment or tracked issue remains the place to record a persistent product defect or required fix. `status` is not a substitute for recorded test counts, CI logs or an agent evaluation trace.

## Parameterized project commands

Extend a component's `commands` and `parameters` in `.agents/commands.json`. A placeholder occupies one complete argv element. `file` and `nodeid` values must refer to an existing file inside the component; `text` is an argv value, never a shell fragment. Selection is explicit, with no implicit arguments appended to unknown scripts.

```json
{
  "components": {
    "api": {
      "path": "backend",
      "parameters": {
        "test-file": {"file": {"type": "file"}},
        "test-node": {"node_id": {"type": "nodeid"}},
        "test-keyword": {"keyword": {"type": "text"}}
      },
      "commands": {
        "test-file": [{"argv": ["python", "-m", "pytest", "{file}"]}],
        "test-node": [{"argv": ["python", "-m", "pytest", "{node_id}"]}],
        "test-keyword": [{"argv": ["python", "-m", "pytest", "-k", "{keyword}"]}]
      }
    }
  }
}
```

```bash
scripts/agent-env.sh test-file --component api --file tests/test_api.py
scripts/agent-env.sh test-node --component api --node-id tests/test_api.py::test_health
scripts/agent-env.sh test-keyword --component api --param keyword=health
```

This is an excerpt, not a full commands.json; preserve its schema, tools, other commands and existing project runner. Adapt the pytest executable to the project's declared installer (`uv run --locked`, a venv, etc.). A declared parameter does not install pytest or prove a test was collected. Use a checked-in script for complex argument construction; never interpolate user input into a shell string. Parameters cannot be combined with `--all` and do not populate an unchanged-input baseline.

## Local metadata change checks

`--changed` is opt-in and has no effect unless that component explicitly lists input globs for that command. Paths are relative to the repository root, can include nested components and config files, and must account for cross-component dependencies. Globs include untracked files. A first run executes normally; successful runs store file paths, sizes, nanosecond modification/change times, registry hash, runner hash and a validation time under `<local_root>/agent-env/change-state.json`. `changes --component NAME --for-command validate --json` reports changed paths, the last success, newest input time and its age. A failure invalidates the baseline. CI and GitHub Actions ignore `--changed` and execute checks.

```json
{
  "components": {
    "api": {
      "path": "backend",
      "change_detection": {
        "lint": {"inputs": ["backend/src/**/*", "backend/tests/**/*", "backend/pyproject.toml"]},
        "validate": {"inputs": ["backend/**/*", "shared/**/*"], "exclude": ["**/__pycache__/**"]}
      }
    }
  }
}
```

```bash
scripts/agent-env.sh validate --component api --changed
scripts/agent-env.sh changes --component api --for-command validate --json
```

The globs and excludes above are illustrative and require review. A skipped check means only that the declared files have unchanged metadata since that command last passed **locally**; it does not establish freshness of services, dependencies, time-sensitive tests, tools, generated files outside the globs, or a clean CI run. File metadata can be preserved across edits or restored from archives. For higher assurance, run without `--changed`, use hashes or the project's own incremental build graph, and keep CI full. Never opt a stateful, deployment or externally dependent check into metadata skipping without a project-specific invalidation rule.

## VS Code task ingestion

`catalog` reads `.vscode/tasks.json` at invocation time, including JSONC comments, trailing commas and platform-specific task overrides. It lists all tasks with their support status; `run-task --task LABEL` runs only a single, literal `type: process` task as an argv array. A task's `cwd` must be inside the repository. Shell tasks, dynamic variables, `dependsOn`, background tasks and run options remain visible in the catalog but require adaptation to a repo-owned command before execution. Process task output and failures use the same local receipts. This deliberately avoids attempting to emulate VS Code input prompts, shell quoting, problem matchers or task graphs.

```bash
scripts/agent-env.sh catalog --json
scripts/agent-env.sh run-task --task 'Run unit tests'
```
