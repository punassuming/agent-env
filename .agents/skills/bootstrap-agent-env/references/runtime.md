# Runner extensions and evidence

The installed runner is a repository-owned command adapter, not a replacement for the project's native task system. `catalog --json` lists command argv, declared parameters, descriptions, change policies and `.vscode/tasks.json` entries. `help` and `list --json` retain their original behavior. Bash and PowerShell wrappers pass the same arguments to the runner.

## Central run registry

`.agents/commands.json` is the single source of named runs. An agent may add any command name and process `argv` steps under an existing broad component. `catalog --json` lists every command; `lookup --component api --for-command test` displays the exact steps, cwd, declared parameters, configured environment overrides, and sandbox needs without running the command or creating cache directories. Bash and PowerShell wrappers accept the same arguments. Review package scripts and transitive effects before executing them.

```json
{
  "components": {
    "api": {
      "path": "backend",
      "commands": {"test": [{"argv": ["uv", "run", "--locked", "pytest"]}]},
      "descriptions": {"test": "Run API tests"},
      "execution": {
        "test": {
          "env": {"UV_CACHE_DIR": "{cache}/uv", "TMPDIR": "{local}/tmp"},
          "create_dirs": ["{cache}/uv", "{local}/tmp"],
          "sandbox": {"network": false, "outside_workspace": false,
                      "elevation": false, "reason": "Dependencies already synchronized"}
        }
      }
    }
  }
}
```

This is an excerpt. Placeholders in `env` and `create_dirs` are `{repo}`, `{component}`, `{local}`, and `{cache}`; directory creation is restricted to the configured ignored local root. The runner also proposes repository-local caches for selected uv, Go, Cargo build and npm tools if their corresponding environment variable is unset. Explicit command `env` values override these proposals. Store secrets in the host environment rather than the tracked registry. Each command's sandbox needs are **advisory observations**: the runner cannot detect every permission boundary, approve itself, enforce network isolation, or grant elevation. The coding agent should inspect the command, run under its current policy when appropriate, diagnose a denial, and request the minimum host permission through its agent interface if justified. Do not interpret `elevation: true` as permission to bypass approval.

## Failure handoff

Every executed step records `last-run.json` in the ignored `<local_root>/agent-env/`. Failed steps retain output under `failures/`, with up to 30 failure records in `failure-history.json`; successful steps use rotating `logs/`. `last-failure.json` remains available after later successes, and `failures` prints the actual saved output. `status` reports the latest run and failure metadata, including whether that component and command later passed. A failure with no output reports its reason. Each process log retains the last 512 KiB of output; the runner prints the full stream as it runs. These logs can contain secrets: keep the local root ignored and review before sharing them.

```bash
scripts/agent-env.sh failures
scripts/agent-env.sh failures --component api --limit 5
scripts/agent-env.sh failures --json
scripts/agent-env.sh status
```

The tracked assessment or issue record holds persistent defects. A local receipt is a diagnostic handoff, not evidence that CI executed the command.

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

## Default local fingerprints

Local validation commands (`validate`, `test`, `lint`, `format-check`, `typecheck`, `build`, `docs-check`) skip **per component and command** when their declared inputs match a previous successful check. Freshly detected components receive a repository-wide scope: in a Git repository the runner collects tracked and non-ignored untracked files, including shared libraries and lockfiles. Git-ignored inputs need explicit inclusion or a forced check. Without Git, it falls back to walking the repository while skipping `.git` and the ignored local state. Only narrow a component scope after identifying all shared inputs and dependencies; an incomplete scope can produce a false skip. An existing component without `change_detection.COMMAND.inputs` always runs. A first check runs and persists a fingerprint only after success. Failure invalidates it.

The fingerprint stores each input path, size, nanosecond mtime and ctime, and a SHA-256 of the sorted metadata; the registry and runner are hashed separately. File contents are not read. Git supplies the default path list without traversing ignored caches. A successful check is cached only when the before and after input fingerprints match; if an input changes during validation, the result cannot justify a future skip. This metadata fingerprint can miss edits that preserve all metadata. Run `--force` to check the selected component, or `--all --force-component NAME` to override a particular component. CI and GitHub Actions always execute checks, regardless of fingerprints or flags. Parameterized commands always run. Bootstrap, debug, deploy and other stateful commands never skip automatically.

```json
{
  "components": {
    "api": {
      "path": "backend",
      "change_detection": {
        "validate": {"inputs": ["backend/**/*", "shared/**/*", "pyproject.toml", "uv.lock"],
                     "exclude": ["**/__pycache__/**", "**/.venv/**"]}
      }
    }
  }
}
```

```bash
scripts/agent-env.sh validate --component api
scripts/agent-env.sh validate --component api --force
scripts/agent-env.sh validate --all --force-component api
scripts/agent-env.sh changes --component api --for-command validate --json
```

`changes` reports changed paths, the metadata hash, last successful check and newest input age. The example narrowed scope requires project-specific review; the generated default is `"**/*"` for each broad component. The old `--changed` flag remains accepted as an alias for the default behavior. Fingerprints are advisory: changes to external services, tools or dependencies outside the declared inputs need a forced run or an expanded input scope.

## VS Code task ingestion

`catalog` reads `.vscode/tasks.json` at invocation time, including JSONC comments, trailing commas and platform-specific task overrides. It lists all tasks with their support status; `run-task --task LABEL` runs only a single, literal `type: process` task as an argv array. A task's `cwd` must be inside the repository. Shell tasks, dynamic variables, `dependsOn`, background tasks and run options remain visible in the catalog but require adaptation to a repo-owned command before execution. Process task output and failures use the same local receipts. This deliberately avoids attempting to emulate VS Code input prompts, shell quoting, problem matchers or task graphs.

```bash
scripts/agent-env.sh catalog --json
scripts/agent-env.sh run-task --task 'Run unit tests'
```
