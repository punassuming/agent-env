# Dot-source from a repo's scripts directory only when these tools are in use.
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$env:UV_CACHE_DIR = Join-Path $repoRoot '.local/cache/uv'
$env:GOCACHE = Join-Path $repoRoot '.local/cache/go-build'
$env:CARGO_TARGET_DIR = Join-Path $repoRoot '.local/cache/cargo-target'
$env:npm_config_cache = Join-Path $repoRoot '.local/cache/npm' # npm only; pnpm store is separate
# GRADLE_USER_HOME also holds configuration and wrapper distributions;
# set it only after checking the project's credentials and init scripts.
