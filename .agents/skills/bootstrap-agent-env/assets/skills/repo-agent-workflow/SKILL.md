---
name: repo-agent-workflow
description: Use this repository's registered commands to diagnose, validate, build, and prepare deployment of a component; update the registry and CI when the project changes.
---

# Work in this repository

Read `AGENTS.md`, `.agents/bootstrap.json`, and `.agents/commands.json`. Use `scripts/agent-env.sh` on Bash systems or `scripts/agent-env.ps1` on PowerShell. `catalog --json` lists project commands and importable VS Code tasks; `lookup --component NAME --for-command COMMAND` shows exact argv, cwd, environment overrides and sandbox needs; `doctor` reports missing tools. Select `--component NAME` for focused checks and `--all` for full validation. For unfamiliar commands, inspect their argv and side effects first. Add new named runs to `.agents/commands.json`, using local cache and temp paths where appropriate. Declared sandbox needs guide host permission requests but do not grant elevation. A project may add parameterized commands such as `test-file --component api --file tests/test_api.py`; inspect the declared command before providing arguments.

When you alter a component, update its checked-in command definitions and CI if its build or tests change. Add components for separately operated repository sections, not every module or package. Keep `validate` in sync with its actual checks. Run focused checks, then broader validation when dependencies are affected. After a failure, use `failures` to read the retained output and `status` to find the failing argv before diagnosing; record persistent defects in the assessment or issue tracker. Local validation skips unchanged Git-visible inputs by default after a prior success; use `--force` or `--force-component NAME` when the inputs are incomplete or a fresh check is needed. CI runs all checks. Report skipped/unconfigured capabilities explicitly.

For a deployment request, inspect the target-specific build, release, smoke-check and rollback procedures. Add them to the repository's command surface when appropriate. Never infer a deployment destination from generic examples, and never run `deploy` as part of validation.
