# agent-env

Agent-guided bootstrap for existing code repositories. It discovers likely toolchains, installs a checked-in command surface, and gives a coding agent a versioned workflow for adapting that surface to the actual project. The installed repository owns its configuration; this source repository is a guide, not a runtime service.

## Start with an agent

Give a coding agent this repository and the target path. Ask it to use [the bootstrap skill](.agents/skills/bootstrap-agent-env/SKILL.md) to **assess**, **install**, or **redeploy**. The agent must review discovered candidates, add project-specific commands and CI, execute checks, and finish the version record. The installer alone cannot infer reliable deployment targets or all monorepo dependencies.

For direct use from a clone with Python 3.11 or newer:

```bash
python -m agent_env assess /path/to/project
python -m agent_env install /path/to/project
# Review and edit /path/to/project/.agents/commands.json; provision its tools.
python -m agent_env finalize /path/to/project
```

PowerShell uses the same `python -m agent_env ...` command; substitute `py -3` if that is your Python launcher. `assess` is read-only. `install` is conservative and repeatable: it adds new detected components, preserves existing command definitions, creates a `pending_version`, and leaves `applied_version` unchanged. `finalize` runs `doctor` and `validate --all` before recording `applied_version`. **Inspect command argv before finalizing**: detection is a proposal, and installed commands can execute project scripts.

## What a target receives

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Short usage instructions; existing content is preserved. |
| `.agents/bootstrap.json` | Applied and pending bootstrap versions; detection evidence and cache path. |
| `.agents/commands.json` | Repo-owned commands per component. Extend it when the project changes. |
| `.agents/bin/runtime.py` | Standalone standard-library command runner; checked into the target. |
| `.agents/skills/repo-agent-workflow/SKILL.md` | Agent guidance for validation, debugging, and deployment preparation. |
| `.claude/skills/repo-agent-workflow/SKILL.md` | Minimal Claude discovery wrapper for the canonical skill. |
| `scripts/agent-env.sh`, `scripts/agent-env.ps1` | Bash and PowerShell entry points to the same runner. |
| `.local/` | Ignored, disposable tool cache and run space. If tracked `.local` content exists, installer selects `.agent-local/` instead. |

The target runner needs Python 3.11+ at execution time. For projects without Python, the agent should implement the same command contract in an already required runtime or task runner; no project should acquire a Python dependency solely for this convention. Native task tools and scripts remain authoritative where they already work.

From a bootstrapped repository:

```bash
./scripts/agent-env.sh help
./scripts/agent-env.sh doctor --json
./scripts/agent-env.sh test --component apps-api
./scripts/agent-env.sh validate --all
```

```powershell
./scripts/agent-env.ps1 help
./scripts/agent-env.ps1 validate --all
```

Commands execute as argv arrays without shell interpolation. An unconfigured command, missing executable, or failed step returns nonzero. The initial `validate` composition covers discovered checks; update it when adding checks. `deploy` remains unconfigured until a target-specific procedure, artifact identity, verification, and rollback path are supplied. The command runner does not perform automatic deployments.

## Projects and platforms

The catalog currently proposes Rust/Cargo, Go, Python/uv, Node/npm or pnpm, and Gradle/Android mappings. It discovers a root project and immediate children of `apps/`, `packages/`, `services/`, and `lib/`; it does not guess arbitrary directory graphs. [Candidate recipes](.agents/skills/bootstrap-agent-env/references/recipes.md) explain what to inspect. Agent-maintained `.agents/commands.json` may contain any additional tool and component. One target is one Git repository or working tree; each component has its own working directory and registered commands.

For separate Git repositories in a developer space, each repository remains independently bootstrapped. Use the optional [workspace manifest](examples/workspace/workspace.json) and `scripts/workspace.py` to coordinate explicit paths:

```bash
python scripts/workspace.py validate --manifest examples/workspace/workspace.json --project api
```

The workspace manifest is an example. Put the coordinator and manifest in the developer space you actually control; do not write into sibling repos without inspecting them. `--all` runs all components within each selected repo. A dependency graph and `--changed` selection are not implemented: the coding agent should add them when their semantics are known, and otherwise use complete validation. Claiming generic affected-component selection across unrelated Git histories would be incorrect.

See [GitHub Actions](examples/ci.github-actions.yml) and [GitLab CI](examples/ci.gitlab.yml) templates. The GitHub template demonstrates Linux, macOS, and Windows Bash/PowerShell entry points. Both templates require target-specific tool provisioning before use; copying them verbatim into a Rust or Android repo will fail. [Bash](examples/env.sh) and [PowerShell](examples/env.ps1) examples show selected cache overrides; the Python runner applies uv, Go, Cargo target, and npm overrides with absolute paths. pnpm's store needs separate project-specific configuration; npm's cache variable is not a pnpm store setting. Do not cache secrets. Gradle user home includes configuration as well as caches, so it is not redirected automatically.

## Redeployment and local extensions

On a later run, the skill reads `.agents/bootstrap.json`, reassesses the current repository, compares `applied_version`, and reconciles new recipes with the project's edited registry, runner, skills, and CI. It should fix obsolete commands and add capabilities supported by evidence. `install` does not overwrite an existing runner or commands. An agent deliberately updates these files, validates them, and finalizes the new version. `pending_version` makes an incomplete attempt visible.

Semantic versioning applies to the skill package; schema versions apply independently to the target's JSON formats. Unknown newer schemas stop installation rather than risk overwriting local work. The target may add domain-specific skills in `.agents/skills`. Codex and Copilot can discover that directory; [the Claude adapter](.claude/skills/bootstrap-agent-env/SKILL.md) demonstrates a minimal wrapper for the source skill. For a target, add Claude wrappers where its discovery requires them.

## Comparable GitHub projects

| Project | Relevant idea | Scope difference |
| --- | --- | --- |
| [anywhere-agents](https://github.com/yzhao062/anywhere-agents) | Pack deployment, drift handling, cross-agent configuration | Wider agent configuration system; some flows compose shared instructions. |
| [cross-agent-skills-template](https://github.com/yammaku/cross-agent-skills-template) | Canonical shared skills with agent-specific adapters and per-project manifests | Focused on skill distribution, not component validation and builds. |
| [project-bootstrap skill](https://github.com/garethrhughes/skills/blob/main/project-bootstrap/SKILL.md) | Agent-led project setup | Primarily an interview and generated instruction output. |
| [jordanburke/agent-env](https://github.com/jordanburke/agent-env) | Same repository name; CLI and Claude plugin | Focused on environment variables and secrets. The name is not unique. |
| [kvcache-ai/AgentENV](https://github.com/kvcache-ai/AgentENV) | Similar name | Distributed execution environment; unrelated scope. |

Our specific focus is a **repo-owned, versioned validation and lifecycle contract**, with the coding agent responsible for adapting and maintaining it. Good ideas to consider later: drift reports, native task-runner adapters, verified component dependency graphs, and skill smoke tests. Avoid introducing all of them before a target repo demonstrates the need.

## Develop this package

```bash
python -m unittest discover -s tests -v
```

The integration tests create disposable Git repos, test monorepo discovery, preserve local edits on reinstall, check failure propagation and finalization, and protect tracked `.local` files. They do not execute deployment or require Rust, Go, Android, or Node toolchains.
