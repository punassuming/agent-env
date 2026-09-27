# Installed contract (schema 1)

`.agents/bootstrap.json` records `skill`, `applied_version`, optional `pending_version`, `schema_version`, selected `local_root`, and toolchain evidence. `.agents/commands.json` records the actual component paths and commands. The latter is repository-owned and may be extended, corrected, or replaced with an equivalent native runner.

The command registry uses `components.NAME.path`, `tools`, and `commands.COMMAND` lists. Each command step has `argv` and optional `argv_windows`. Commands execute without a shell from their component directory. A missing command returns nonzero and reports `UNCONFIGURED`. `validate` is an explicit composition; it must be revised when new checks are added.

The repo-owned runner offers `help`, `list --json`, `doctor --json`, and any registered command with `--component NAME` or `--all`. Bash and PowerShell wrappers invoke the same runner. `doctor` is read-only. Running a command can create cache files and can have other effects declared by that command; inspect new candidates before execution.

Each repository independently checks in its runner, registry, skills, scripts, and CI. A developer workspace with separate Git repos uses an explicit manifest to invoke each repo's command surface; it is not a replacement for per-repo configuration. Record dependent component relationships locally when a monorepo requires affected-component validation. If this metadata is missing or unreliable, run the broader suite.

The version record is a review trigger, not an ownership ledger. The installer stages `pending_version`; only a successful validation and `finalize` moves it to `applied_version`. Preserve existing commands on reinstallation. A coding agent reconciles new upstream recipes with local decisions.
