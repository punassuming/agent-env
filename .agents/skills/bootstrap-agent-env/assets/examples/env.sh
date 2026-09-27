#!/usr/bin/env bash
# Source this file from the repo root only when these tools are in use.
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
export UV_CACHE_DIR="$repo_root/.local/cache/uv"
export GOCACHE="$repo_root/.local/cache/go-build"
export CARGO_TARGET_DIR="$repo_root/.local/cache/cargo-target"
export npm_config_cache="$repo_root/.local/cache/npm" # npm only; pnpm store is separate
# GRADLE_USER_HOME also holds configuration and wrapper distributions;
# set it only after checking the project's credentials and init scripts.
