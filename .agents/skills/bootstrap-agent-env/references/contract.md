# Installed contract (schema 1)

`.agents/bootstrap.json` records `skill`, `applied_version`, optional `pending_version`, `schema_version`, selected `local_root`, and toolchain evidence. `.agents/commands.json` records the actual component paths and commands. The latter is repository-owned and may be extended, corrected, or replaced with an equivalent native runner.

`.agents/runtime-deployment.json` records the installed runner hash for future safe upgrades. A redeploy updates `.agents/bin/runtime.py` only when its current content matches the previous managed hash. If the receipt is absent or the runner changed locally, the installer preserves the file and reports a review action; copy or merge the newer runner deliberately, then run its checks. Do not use a pending skill version as proof that an older installed runner supports newer commands.

The command registry uses `components.NAME.path`, `tools`, and `commands.COMMAND` lists. Each command step has `argv` and optional `argv_windows`. Commands execute without a shell from their component directory. A missing command returns nonzero and reports `UNCONFIGURED`. `validate` is an explicit composition; it must be revised when new checks are added.

Optional `components.NAME.parameters.COMMAND` declares `file`, `nodeid`, or `text` parameters for whole-argv `{name}` placeholders. Optional `components.NAME.change_detection.COMMAND.inputs` lists repository-relative globs for opt-in local `--changed`; `exclude` filters outputs. Omit these features when the project does not benefit from them. `catalog --json` returns full registered argv, parameter schemas and available `.vscode/tasks.json` tasks. Only literal VS Code process tasks may be executed through `run-task --task LABEL`; other entries are discoverable but require adaptation. See `runtime.md` for safety boundaries and examples.

Workspace members can set `bootstrap_from: root`. Running `bootstrap --all` then runs root installation once; selecting that member alone delegates bootstrap to the root. Ordinary validation remains component-specific.

The repo-owned runner offers `help`, `list --json`, `doctor --json`, and any registered command with `--component NAME` or `--all`. Bash and PowerShell wrappers invoke the same runner. `doctor` is read-only. Running a command can create cache files and can have other effects declared by that command; inspect new candidates before execution.

Executed steps persist their latest receipt and bounded log under ignored `<local_root>/agent-env/`. `status` reads the latest run and retained last failure. A passing `--changed` skip means metadata matched an earlier **local** success on explicitly declared inputs, not that a check ran now. CI never skips on this basis. Failure receipts and changed-input snapshots are disposable and are not tracked registry state.

Each repository independently checks in its runner, registry, skills, scripts, and CI. A developer workspace with separate Git repos uses an explicit manifest to invoke each repo's command surface; it is not a replacement for per-repo configuration. Record dependent component relationships locally when a monorepo requires affected-component validation. If this metadata is missing or unreliable, run the broader suite.

The version record is a review trigger, not an ownership ledger. The installer stages `pending_version`; only a successful validation and `finalize` moves it to `applied_version`. Preserve existing commands on reinstallation. A coding agent reconciles new upstream recipes with local decisions.
