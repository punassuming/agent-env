# Candidate recipes

Use detection as a hypothesis. Read the project's configuration before registering a command; run a harmless probe when possible. Do not invent project scripts or assume optional tools are installed.

| Evidence | Install/bootstrap | Validate candidates | Notes |
| --- | --- | --- | --- |
| `Cargo.toml` | `cargo fetch --locked` if appropriate | `cargo fmt --all -- --check`; `cargo clippy --all-targets -- -D warnings`; `cargo test`; `cargo build` | rustfmt and clippy are optional rustup components. |
| `go.mod` or `go.work` | `go mod download` where applicable | `gofmt` difference check; `go vet ./...`; `go test ./...`; `go build ./...` | Determine workspace and module scope. |
| `pyproject.toml` + `uv.lock` | `uv sync --locked` | `uv run --locked pytest`, Ruff only if declared | Workspace members can inherit a root lockfile and bootstrap. Use `UV_CACHE_DIR`; tests may be elsewhere. |
| Python without uv | existing install mechanism | existing test/lint/typecheck commands | Never switch package manager silently. |
| `package.json` + `package-lock.json` | `npm ci` | actual scripts from package.json | Reject placeholder test scripts. |
| `package.json` + `pnpm-lock.yaml` | `pnpm install --frozen-lockfile` | actual scripts from package.json | Members inherit the root lockfile and bootstrap once at the workspace root. |
| Gradle wrapper | wrapper | `check`, `build`, or project-specific tasks | On Windows invoke `gradlew.bat`; inspect wrapper and plugins. |
| Android Gradle app | wrapper + Android SDK | module/variant `lint`, unit test and `assembleDebug` tasks | Identify modules, variants, SDK, and signing needs. |

For additional tools, extend this catalog and the target's local registry. Prefer documented cache overrides under `.local/cache` only if confinement is needed. `GRADLE_USER_HOME` holds config and wrapper distributions as well as cache; changing it may change credentials and behavior. Keep environment setup consistent in Bash, PowerShell and CI via the repo runner; use tool-native configuration where that is more reliable.
