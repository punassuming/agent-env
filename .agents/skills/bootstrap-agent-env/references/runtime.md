# Runner extensions and evidence

The installed runner is a repository-owned command adapter, not a replacement for the project's native task system. `catalog --json` lists command argv, declared parameters, descriptions, change policies and `.vscode/tasks.json` entries. `help` and `list --json` retain their original behavior. Bash and PowerShell wrappers pass the same arguments to the runner.

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

Local validation commands (`validate`, `test`, `lint`, `format-check`, `typecheck`, `build`, `docs-check`) skip **per component and command** when their declared inputs match a previous successful check. Freshly detected components receive a broad recursive input scope for their component path, with common cache and output directories excluded. Inspect and extend those globs for shared libraries, root configuration, lockfiles, generated inputs and dependencies; incomplete inputs can produce false skips. An existing component without `change_detection.COMMAND.inputs` always runs. A first check runs and persists a fingerprint only after success. Failure invalidates it.

The fingerprint stores each input path, size, nanosecond mtime and ctime; it also stores a SHA-256 of this sorted metadata plus the registry and runner hashes. The scan prunes `.git`, the configured local cache and declared output trees for ordinary recursive paths. It includes untracked files in the declared paths. This is a fast metadata fingerprint: edits that preserve all metadata can escape detection. Run `--force` to check the selected component, or `--all --force-component NAME` to override a particular component. CI and GitHub Actions always execute checks, regardless of fingerprints or flags. Parameterized commands always run. Bootstrap, debug, deploy and other stateful commands never skip automatically.

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

`changes` reports changed paths, the metadata hash, last successful check and newest input age. The old `--changed` flag remains accepted as an alias for the default behavior. Fingerprints are advisory: changes to external services, tools or dependencies outside the declared inputs need a forced run or an expanded input scope.

## VS Code task ingestion

`catalog` reads `.vscode/tasks.json` at invocation time, including JSONC comments, trailing commas and platform-specific task overrides. It lists all tasks with their support status; `run-task --task LABEL` runs only a single, literal `type: process` task as an argv array. A task's `cwd` must be inside the repository. Shell tasks, dynamic variables, `dependsOn`, background tasks and run options remain visible in the catalog but require adaptation to a repo-owned command before execution. Process task output and failures use the same local receipts. This deliberately avoids attempting to emulate VS Code input prompts, shell quoting, problem matchers or task graphs.

```bash
scripts/agent-env.sh catalog --json
scripts/agent-env.sh run-task --task 'Run unit tests'
```
