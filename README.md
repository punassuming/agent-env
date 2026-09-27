# agent-env

Agent-guided bootstrap for existing code repositories. It discovers likely toolchains, installs a checked-in command surface, and gives a coding agent a versioned workflow for adapting that surface to the actual project. The installed repository owns its configuration. Its tool recipes are proposals, and the agent should select only checks supported by project evidence. This repository is a versioned registry of installable skills and agent definitions; the environment bootstrap installs the default entries and then a coding agent adapts them to the project.

## Start with an agent

Give a coding agent this repository and the target path. Ask it to use [the bootstrap skill](.agents/skills/bootstrap-agent-env/SKILL.md) to **assess**, **install**, or **redeploy**. The agent must review discovered candidates, add project-specific commands and CI, execute checks, and finish the version record. The installer alone cannot infer reliable deployment targets or all monorepo dependencies. The agent writes a checked-in `.agents/assessment.md` following [the assessment guide](.agents/skills/bootstrap-agent-env/references/assessment.md), recording tool selection, capability coverage, validation results, gaps, and opportunities. The assessment format is adaptable to the project; a missing toolchain can be added locally rather than treated as unsupported. [Sandbox diagnostics](.agents/skills/bootstrap-agent-env/references/sandbox.md) cover cache, temporary files, network access, and tool-specific limitations.

For direct use from a clone with Python 3.11 or newer:

```bash
python -m agent_env assess /path/to/project
python -m agent_env install /path/to/project
# Review and edit /path/to/project/.agents/commands.json; provision its tools.
python -m agent_env finalize /path/to/project
```

PowerShell uses the same `python -m agent_env ...` command; substitute `py -3` if that is your Python launcher. `assess` is read-only. `install` is conservative and repeatable: it adds new detected components, preserves existing command definitions, creates a `pending_version`, and leaves `applied_version` unchanged. `finalize` runs `doctor` and `validate --all` before recording `applied_version`. **Inspect command argv before finalizing**: detection is a proposal, and installed commands can execute project scripts.

## Registry architecture

[`.agents/registry.json`](.agents/registry.json) names each skill or agent definition, its version, source file or directory, target destinations, and whether it installs by default. Canonical bootstrap implementation, cross-platform wrappers, workflow skill, examples, and runtime live inside [the bootstrap skill](.agents/skills/bootstrap-agent-env/SKILL.md): `scripts/` holds code, `references/` holds guidance, and `assets/` holds files copied to targets. The Python `agent_env` package is a thin dispatcher and registry manager; a bootstrapped repository keeps a complete copy of the skill, registry manifest and canonical agent sources. It can reassess itself with `.agents/skills/bootstrap-agent-env/scripts/bootstrap.py` and install local additions with `.agents/skills/bootstrap-agent-env/scripts/registry.py`.

```bash
python -m agent_env registry plan /path/to/project
python -m agent_env registry install /path/to/project
python -m agent_env registry plan /path/to/project --select bootstrap-agent-env
```

Repeat `--select` for multiple entries; without it, all defaults install. Any skill folder with a `SKILL.md` under `.agents/skills/` and any file under `.agents/agents/<provider>/` installs by default without a manifest change. Add explicit entries to the manifest when versions, alternate source paths, destinations, or selection behavior need configuration. A deployment receipt at `.agents/registry-deployment.json` records file hashes and item names. Reinstall updates unchanged managed files, reports local edits as conflicts, and never deletes files. Registry deployment lays down reusable instructions; `install` also discovers components and scaffolds runnable commands. Adapt recipes, agents, CI and the component map after inspecting the project.

Claude agent definitions install to `.claude/agents/`, Copilot definitions to `.github/agents/`, and canonical skills to `.agents/skills/` with Claude discovery copies in `.claude/skills/`. Provider file formats remain separate sources in the registry. The names and prompt text are examples to customize per project.

## What a target receives

| Path | Purpose |
| --- | --- |
| `AGENTS.md` | Short usage instructions; existing content is preserved. |
| `.agents/bootstrap.json` | Applied and pending bootstrap versions; detection evidence and cache path. |
| `.agents/registry-deployment.json` | Installed skills and agents with hashes for safe redeployment. |
| `.agents/skills/bootstrap-agent-env/` | Complete versioned bootstrap skill with its code, references and assets. |
| `.agents/commands.json` | Repo-owned commands per component. Extend it when the project changes. |
| `.agents/bin/runtime.py` | Standalone standard-library command runner; checked into the target. |
| `.agents/skills/repo-agent-workflow/SKILL.md` | Agent guidance for validation, debugging, and deployment preparation. |
| `.claude/agents/repo-maintainer.md`, `.github/agents/repo-maintainer.agent.md` | Example agent definitions for Claude and Copilot. |
| `.claude/skills/repo-agent-workflow/SKILL.md` | Minimal Claude discovery wrapper for the canonical skill. |
| `scripts/agent-env.sh`, `scripts/agent-env.ps1` | Bash and PowerShell entry points to the same runner. |
| `.local/` | Ignored, disposable tool cache and run space. If tracked `.local` content exists, installer selects `.agent-local/` instead. |

The target runner needs Python 3.11+ at execution time. For projects without Python, the agent should implement the same command contract in an already required runtime or task runner; no project should acquire a Python dependency solely for this convention. Native task tools and scripts remain authoritative where they already work.

## Sync to your home directory

From a local checkout, preview then sync its tracked files into `~/.agents/agent-env` and expose default registered skills at `~/.agents/skills/`:

```bash
python -m agent_env home plan
python -m agent_env home sync
python -m agent_env home status
```

Use `--claude` with `plan` and `sync` to also install Claude skill copies and registered Claude agent definitions into `~/.claude/`. PowerShell uses the same commands with `python` or `py -3`. `--home PATH` selects another `.agents` directory. Home sync is local and does not fetch changes from GitHub; update the source checkout first, then sync. The copied `~/.agents/agent-env` is a snapshot, not a Git checkout. You may instead clone the repository directly into `~/.agents/agent-env`, update it with Git, and run home sync there; the command recognizes that location and updates the exposed skill copies.

The command stores a hash record in `~/.agents/agent-env-sync.json`. It can update previously synced files but aborts a sync if any destination has a local edit or an unrelated file at the same path. It never deletes destination files that are absent upstream; inspect stale files during an upgrade. It does not modify skills outside the registered destinations.

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

The catalog proposes Rust/Cargo, Go, Python/uv and Django, Node/npm or pnpm, C#/.NET, static HTML and Gradle/Android mappings. The detector searches a root project and immediate children of `apps/`, `packages/`, `services/`, and `lib/`; the agent must inspect deeper folders and separate repositories itself. [Candidate recipes](.agents/skills/bootstrap-agent-env/references/recipes.md) explain what to inspect. Existing [Docker, Compose, Kubernetes and Helm artifacts](.agents/skills/bootstrap-agent-env/references/infrastructure.md) warrant their own non-deploy validation when used in the release path. A working application test does not establish that an image builds or a manifest renders. Agent-maintained `.agents/commands.json` may contain any additional tool and component. One target is one Git repository or working tree; each component has its own working directory and registered commands.

For separate Git repositories in a developer space, each repository remains independently bootstrapped. Use the optional [workspace manifest](.agents/skills/bootstrap-agent-env/assets/examples/workspace/workspace.json) and the [workspace coordinator](.agents/skills/bootstrap-agent-env/assets/scripts/workspace.py) to coordinate explicit paths:

```bash
python .agents/skills/bootstrap-agent-env/assets/scripts/workspace.py validate --manifest workspace.json --project api
```

The workspace manifest is an example. Put the coordinator and manifest in the developer space you actually control; do not write into sibling repos without inspecting them. `--all` runs all components within each selected repo. A dependency graph and `--changed` selection are not implemented: the coding agent should add them when their semantics are known, and otherwise use complete validation. Claiming generic affected-component selection across unrelated Git histories would be incorrect.

See [GitHub Actions](.agents/skills/bootstrap-agent-env/assets/examples/ci.github-actions.yml) and [GitLab CI](.agents/skills/bootstrap-agent-env/assets/examples/ci.gitlab.yml) templates. The GitHub template demonstrates Linux, macOS, and Windows Bash/PowerShell entry points. Both templates require target-specific tool provisioning before use; copying them verbatim into a Rust or Android repo will fail. [Bash](.agents/skills/bootstrap-agent-env/assets/examples/env.sh) and [PowerShell](.agents/skills/bootstrap-agent-env/assets/examples/env.ps1) examples show selected cache overrides; the Python runner applies uv, Go, Cargo target, and npm overrides with absolute paths. pnpm's store needs separate project-specific configuration; npm's cache variable is not a pnpm store setting. Do not cache secrets. Gradle user home includes configuration as well as caches, so it is not redirected automatically.

## Redeployment and local extensions

On a later run, the skill reads `.agents/bootstrap.json`, reassesses the current repository, compares `applied_version`, and reconciles new recipes with the project's edited registry, runner, skills, and CI. It should fix obsolete commands and add capabilities supported by evidence. `install` does not overwrite an existing runner or commands. An agent deliberately updates these files, validates them, and finalizes the new version. `pending_version` makes an incomplete attempt visible.

Semantic versioning applies to the skill package; schema versions apply independently to the target's JSON formats. Unknown newer schemas stop installation rather than risk overwriting local work. The target may add domain-specific skills in `.agents/skills`; register reusable upstream skills in `.agents/registry.json`. Codex and Copilot can discover that directory; [the Claude adapter](.claude/skills/bootstrap-agent-env/SKILL.md) demonstrates a minimal wrapper for the source skill. For a target, add Claude wrappers where its discovery requires them.

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

The registry tests deploy a synthetic new skill and agent definition, verify managed upgrades and local-edit conflicts. The integration tests create disposable Git repos, test monorepo discovery, preserve local edits on reinstall, check failure propagation and finalization, and protect tracked `.local` files. They do not execute deployment or require Rust, Go, Android, or Node toolchains.

The CI matrix runs on Linux, macOS, and Windows. Four independently authored [scenario fixtures](tests/scenarios) exercise a Python/uv workspace, a pnpm workspace, a flavored Android/Gradle project, and separate Go/Rust repositories coordinated by a workspace manifest. They use fake executables to check command routing without downloading toolchains. POSIX fake-tool scenarios skip Windows; core command and home-sync tests run there. The Android scenario confirms that variant tasks need an agent's project-specific selection; the bootstrap does not guess flavors or release signing.

For agent behavior trials, [the skill evaluation protocol](.agents/skills/bootstrap-agent-env/references/evaluation.md) and its `scripts/evaluations/prepare.py`, `prepare_web_cases.py`, and `prepare_stack_cases.py` create disposable, committed repositories covering Python, Node, FastAPI/pnpm/React layouts, Android/Kotlin, Go, Rust, C#, Django, static HTML, Docker, Compose, Kubernetes and Helm. Give each agent the skill, target, generated `EVAL_ENV.md`, and bootstrap request; inspect its edited files and validation output. The trial instructions describe network and filesystem scope but do not enforce per-agent isolation. A pending version is expected when compilers, SDKs, services or release checks are unavailable. These cases exercise skill interpretation; they do not substitute for builds on provisioned CI runners.
