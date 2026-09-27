---
name: repo-agent-workflow
description: Use this repository's registered commands to diagnose, validate, build, and prepare deployment of a component; update the registry and CI when the project changes.
---

# Work in this repository

Read `AGENTS.md`, `.agents/bootstrap.json`, and `.agents/commands.json`. Use `scripts/agent-env.sh` on Bash systems or `scripts/agent-env.ps1` on PowerShell. `catalog --json` lists project commands and importable VS Code tasks; `doctor` reports missing tools. Select `--component NAME` for focused checks and `--all` for full validation. For unfamiliar commands, inspect their argv and side effects first. A project may add parameterized commands such as `test-file --component api --file tests/test_api.py`; inspect the declared command before providing arguments.

When you alter a component, update its checked-in command definitions and CI if its build or tests change. Add new components to the registry. Keep `validate` in sync with its actual checks. Run focused checks, then broader validation when dependencies are affected. After a failure, use `status` to find the last failing argv and ignored log before diagnosing; record persistent defects in the assessment or issue tracker. Local `--changed` may skip only explicitly declared unchanged inputs after a prior success; it is advisory and never replaces full CI. Report skipped/unconfigured capabilities explicitly.

For a deployment request, inspect the target-specific build, release, smoke-check and rollback procedures. Add them to the repository's command surface when appropriate. Never infer a deployment destination from generic examples, and never run `deploy` as part of validation.
