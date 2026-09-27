---
name: bootstrap-agent-env
description: Assess, install, extend, or redeploy a repository's agent environment. Use for cross-platform validation, CI, cache, component commands, agent skills, monorepos, and multi-repo developer workspaces.
---

# Bootstrap and maintain an agent environment

Current version: **0.3.0**. Read `references/recipes.md` for candidate toolchain commands, `references/contract.md` for the installed contract, and `references/assessment.md` for the required assessment output. Use `references/evaluation.md` when testing or revising this skill with coding agents. The repository's actual commands and requirements take precedence over these examples.

## Assess and install

1. Inspect Git status, existing AGENTS.md/CLAUDE.md, CI, lockfiles, scripts, tests, build tools, container definitions, and deployment paths. Inspect root and nested packages. Ask for missing deployment targets or credentials only when needed for the actual deployment.
2. Write `.agents/assessment.md` following `references/assessment.md`: record evidence, selected tools, every lifecycle capability, validation coverage, gaps and opportunities, execution results, cache and deployment decisions. Update it as the work progresses. Run `python -m agent_env assess TARGET` from this source package when Python is available. Its detections are **proposals**, not proof. Investigate gaps and additional languages, packages, services, and tool-specific config; amend the proposals.
3. For an install request, run `python -m agent_env install TARGET`. It deploys registered skills and agent definitions, creates a version record and commands registry, installs Bash/PowerShell wrappers, and sets an ignored local cache root. The installer preserves existing commands, so inspect and fix unsuitable candidates in `.agents/commands.json` before executing them.
4. Extend the target's registry, scripts, docs, skills, and CI based on observed behavior. Use the installed `.agents/skills/bootstrap-agent-env/scripts/bootstrap.py` for later local reassessment; use a newer registry checkout to upgrade. If Python is unavailable in the target environment, implement the same command contract with an existing repo-native runner and document its entry points.
5. Map components and dependencies. Validate a component directly; validate dependents on changes when the graph is known; otherwise run all affected candidates. Separate repos may use `assets/scripts/workspace.py` from this skill with an explicit developer workspace manifest, while each repo retains its own runner.
6. Run help, doctor, selected checks, and `validate --all` with real failures and successful paths. Add CI using the same registry; provision required toolchains there. Do not mark an unavailable check successful. Record changes and verification in `.agents/assessment.md`.
7. Only after satisfactory validation, run `python -m agent_env finalize TARGET` in this source package to record the applied skill version. If validation cannot complete, keep a pending version and report it.

Read `../../registry.json` from the source checkout to see available skills and agent definitions; use `python -m agent_env registry plan TARGET` and `python -m agent_env registry install TARGET` to deploy defaults, or repeat `--select ITEM` to choose specific entries. Add new skills and agent definitions there with their source paths, versions, and destinations. The generated `.agents/registry-deployment.json` records file hashes for safe updates. Any valid child directory of `.agents/skills/` containing `SKILL.md` deploys by default even without a manifest entry. Any agent definition or associated file under `.agents/agents/<provider>/` also deploys by default (`claude` to `.claude/agents/`, `copilot` to `.github/agents/`, other providers to `.agents/agents/<provider>/`). Explicit manifest entries add versions, alternate source paths, destinations, and default selection. This allows future skills and agents to be added by folder alone. For a bootstrapped repository, use `python .agents/skills/bootstrap-agent-env/scripts/registry.py plan|install TARGET` to deploy newly added local skills and agents; its installed manifest and definitions are retained. For a reusable personal installation, run `python -m agent_env home plan` then `python -m agent_env home sync` from a source checkout. The latter stores the source under `~/.agents/agent-env` and exposes this skill in `~/.agents/skills`. If a destination differs from the last synced version, resolve the conflict rather than overwriting local changes. Use `--claude` to install a canonical skill copy into `~/.claude/skills` as well.

## Redeploy / upgrade

1. Read `.agents/bootstrap.json` and compare `applied_version` with this skill's current version. Review the installed code, current repo, selected tools, local extensions, CI, and Git diff; do not overwrite repo edits from upstream templates.
2. Review the deployed registry receipt and any locally edited skills or agents. Run assessment again; add relevant new recipes, resolve stale mappings, improve local workflow skills, and update cross-platform scripts as needed. Update `.agents/bin/runtime.py` deliberately if the upstream runtime has fixes. Record changes as pending, verify, then finalize.
3. Keep the installed registry authoritative for this repo. A version mismatch calls for review, not automatic regeneration. Refuse to mutate an unknown newer schema; explain the needed migration.

## Operations

- `assess`: read-only report with evidence, detected/unconfigured capabilities and opportunities.
- `install`: write and adapt the target repo; no deploy action.
- `validate`: execute only registered deterministic commands and propagate failures.
- `deploy-plan`: show artifact, target, credentials prerequisite, smoke check, and rollback path.
- `deploy`: only after an explicit request and project-specific target configuration. Verify built artifact identity and health. Never infer a production target from a generic template.

Keep cache and temporary state under the target's recorded `.local/` (or chosen alternative); preserve preexisting tracked `.local` contents. Do not store secrets in cache. Claude Code uses a `.claude/skills` adapter to discover canonical `.agents/skills` skills. Registry deployment includes `.claude/agents` and `.github/agents` provider definitions. If CLAUDE.md masks AGENTS.md, import the latter with `@AGENTS.md` rather than duplicating it.
