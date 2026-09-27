---
name: bootstrap-agent-env
description: Assess, install, extend, or redeploy a repository's agent environment. Use for cross-platform validation, CI, cache, component commands, agent skills, monorepos, and multi-repo developer workspaces.
---

# Bootstrap and maintain an agent environment

Current version: **0.2.0**. Read `references/recipes.md` for candidate toolchain commands and `references/contract.md` for the installed contract. The repository's actual commands and requirements take precedence over these examples.

## Assess and install

1. Inspect Git status, existing AGENTS.md/CLAUDE.md, CI, lockfiles, scripts, tests, build tools, container definitions, and deployment paths. Inspect root and nested packages. Ask for missing deployment targets or credentials only when needed for the actual deployment.
2. Run `python -m agent_env assess TARGET` from this source package when Python is available. Its detections are **proposals**, not proof. Investigate gaps and additional languages, packages, services, and tool-specific config; amend the proposals.
3. For an install request, run `python -m agent_env install TARGET`. It creates a version record, commands registry, runnable Bash/PowerShell wrappers, a local workflow skill, and ignored local cache root. The installer preserves existing commands, so inspect and fix unsuitable candidates in `.agents/commands.json` before executing them.
4. Extend the target's registry, scripts, docs, skills, and CI based on observed behavior. Do not depend on this source package after installation. If Python is unavailable in the target environment, implement the same command contract with an existing repo-native runner and document its entry points.
5. Map components and dependencies. Validate a component directly; validate dependents on changes when the graph is known; otherwise run all affected candidates. Separate repos may use `scripts/workspace.py` with an explicit developer workspace manifest, while each repo retains its own runner.
6. Run help, doctor, selected checks, and `validate --all` with real failures and successful paths. Add CI using the same registry; provision required toolchains there. Do not mark an unavailable check successful. Record changes and verification.
7. Only after satisfactory validation, run `python -m agent_env finalize TARGET` in this source package to record the applied skill version. If validation cannot complete, keep a pending version and report it.

For a reusable personal installation, run `python -m agent_env home plan` then `python -m agent_env home sync` from a source checkout. The latter stores the source under `~/.agents/agent-env` and exposes this skill in `~/.agents/skills`. If a destination differs from the last synced version, resolve the conflict rather than overwriting local changes. Use `--claude` to install a canonical skill copy into `~/.claude/skills` as well.

## Redeploy / upgrade

1. Read `.agents/bootstrap.json` and compare `applied_version` with this skill's current version. Review the installed code, current repo, selected tools, local extensions, CI, and Git diff; do not overwrite repo edits from upstream templates.
2. Run assessment again; add relevant new recipes, resolve stale mappings, improve local workflow skills, and update cross-platform scripts as needed. Update `.agents/bin/runtime.py` deliberately if the upstream runtime has fixes. Record changes as pending, verify, then finalize.
3. Keep the installed registry authoritative for this repo. A version mismatch calls for review, not automatic regeneration. Refuse to mutate an unknown newer schema; explain the needed migration.

## Operations

- `assess`: read-only report with evidence, detected/unconfigured capabilities and opportunities.
- `install`: write and adapt the target repo; no deploy action.
- `validate`: execute only registered deterministic commands and propagate failures.
- `deploy-plan`: show artifact, target, credentials prerequisite, smoke check, and rollback path.
- `deploy`: only after an explicit request and project-specific target configuration. Verify built artifact identity and health. Never infer a production target from a generic template.

Keep cache and temporary state under the target's recorded `.local/` (or chosen alternative); preserve preexisting tracked `.local` contents. Do not store secrets in cache. Claude Code may need a thin `.claude/skills` adapter to discover canonical `.agents/skills` skills. If CLAUDE.md masks AGENTS.md, import the latter with `@AGENTS.md` rather than duplicating it.
