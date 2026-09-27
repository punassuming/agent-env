# Running project tools in agent sandboxes

Use this as a diagnostic guide, not a policy file. A skill or environment variable cannot expand a sandbox's permitted filesystem roots or network domains. Codex and Claude have separate filesystem and network controls; first establish which control actually blocked a command. See [Codex sandboxing](https://developers.openai.com/codex/concepts/sandboxing) and [Claude sandboxing](https://code.claude.com/docs/en/sandboxing).

## Diagnose before changing configuration

1. Run the project's native `--version` or `--help`, then the repo runner's `doctor`. Record the executable path, working directory, environment and exact error. `doctor` checks executable presence and the chosen local directory; it does **not** prove network access, actual writes, tool correctness, or that tests exist.
2. Distinguish `ENOENT`/missing executable (tool not provisioned), filesystem denial or permission error (path outside writable roots), DNS/connection/host-denied (network), invalid lockfile, and zero collected tests. Never label any of these a lint/test pass.
3. Inspect where the tool writes: install cache, build output, test cache, temp files, user configuration, and report files can have different locations. Use project lockfiles and native task definitions; do not install a linter simply because a recipe lists it.
4. Before invoking registered commands, inspect whether they resolve dependencies implicitly. `uv run` can lock/sync before executing; a pnpm invocation can trigger package-manager setup or dependency resolution even when the argv appears to request only a filtered command. Under an offline evaluation or sandbox policy, inspect lockfile, installed modules, package-manager pin and launcher before **any** pnpm execution; avoid even `pnpm --filter ...` when they are missing. Use `uv run --no-sync --offline` only when its environment already exists, or `pnpm install --offline --frozen-lockfile` only when its store and lockfile are ready. If prerequisites are absent, record the check as blocked and provision dependencies in authorized CI. A writable cache cannot bypass an egress restriction. Do not silently switch to a broader sandbox policy.
5. For sibling repositories, grant only their actual roots through the agent's workspace settings, or run an agent separately in each repository. A workspace manifest lists projects but does not grant filesystem permissions.

## Cache placement and reproducibility

Choose a writable, ignored local root (normally `.local/`, with a collision-safe alternative). Keep disposable caches under it where the tool supports an override. Make the cache path absolute for tools that require it. Preserve a preexisting tool or user override unless it is the cause of the failure; test an actual command with the proposed setting. Avoid overriding `HOME`/`USERPROFILE` wholesale: these also hold credentials, config, Git identity and toolchain state. Prefer tool-specific variables, and keep real secrets outside ignored caches. A cache only speeds up work; locked dependencies and declared tool versions establish reproducibility.

| Tool | Possible sandbox-local setting | Check before enabling |
| --- | --- | --- |
| uv | `UV_CACHE_DIR=<root>/.local/cache/uv` | Keep on the same filesystem as the virtual environment when practical; `uv sync --locked` needs the lockfile and dependencies. |
| Go | `GOCACHE=<absolute path>`; optionally `GOMODCACHE=<path>` | Build cache and module download cache are distinct; inspect `go env` and private module authentication. |
| Rust | `CARGO_TARGET_DIR=<path>` | This relocates build output, not Cargo's registry and git caches; `CARGO_HOME` also contains installed binaries and configuration, so relocate it only deliberately. |
| npm | `npm_config_cache=<path>` | Applies to npm; verify pnpm's own store configuration separately. |
| Ruff | `RUFF_CACHE_DIR=<path>` | Set only if its existing cache location causes a problem. |
| pytest | `-o cache_dir=<path>` | Set only if `.pytest_cache` is disallowed; test temporary-file fixtures separately. |
| Gradle | `GRADLE_USER_HOME=<path>` | Contains init scripts, credentials/config and wrapper distributions as well as cache; assess consequences before moving it. |

A prompt that prohibits downloads does not enforce a network boundary; test-agent runtimes can still inherit host egress and warm global package stores. Record observed downloads, lockfile mutations and package scripts if a broad command starts them, then stop and adjust. Official details: [uv run/sync](https://docs.astral.sh/uv/concepts/projects/sync/) and [pnpm offline install](https://pnpm.io/cli/install/).

The bundled runner currently proposes uv, Go build, Cargo build, and npm overrides when those tools are detected. Its choices are editable repository code, not mandatory policy. The Bash and PowerShell examples illustrate settings; amend or omit them for the chosen tools. Source details: [uv caching](https://docs.astral.sh/uv/concepts/cache/), [Go environment](https://pkg.go.dev/cmd/go), [Cargo environment](https://doc.rust-lang.org/cargo/reference/environment-variables.html), [npm config](https://docs.npmjs.com/cli/v11/using-npm/config/), [Ruff settings](https://docs.astral.sh/ruff/settings/), [pytest settings](https://docs.pytest.org/en/latest/reference/reference.html), and [Gradle directories](https://docs.gradle.org/current/userguide/directory_layout.html).

Use the host's supported writable temp location for short-lived files. Claude may redirect `$TMPDIR` for sandboxed commands; do not assume the same path in an unsandboxed shell. In Codex, a repo-local ignored directory is useful for generated outputs that must remain visible to the agent. On Windows, prefer tool-native environment variables through PowerShell and ensure the chosen paths exist. On CI, restore only disposable caches, never `.agents/commands.json`, source files, secrets or a virtual environment built for a different platform. Validate on at least one clean environment to catch cache-dependent success.
