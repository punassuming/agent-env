# Workspace assessment and handoff

For every bootstrap or redeploy, write `.agents/assessment.md` in the target. Use a compact table, sections, or another readable structure that fits the project. Include these facts, with evidence rather than a fixed set of columns:

- Components and boundaries: root packages, workspaces, independent repos, and the files/CI that identify them.
- Selected toolchain and version source; existing native commands; skills and agent definitions deployed; the reason for each added command.
- Actual available entry points for setup, test, lint, format, build, docs, debug and deployment. Mark irrelevant or missing capabilities `not applicable` or `unconfigured` with a reason. Add capabilities specific to the project (type checks, security scans, schema checks, Android variants, integration services, etc.).
- What `validate` runs, what CI provisions, commands and exit status observed locally, failures, and what was not exercised. Separate application, container build, Compose, rendered manifest/chart and live deployment coverage when those artifacts exist. A zero-test test runner, echo-only wrapper, empty lint scope, or build task missing its executable is incomplete coverage even if a command exits zero.
- Sandbox observations: writable roots, tool/cache/temp locations and network or permission blocks; the selected ignored local root and whether any existing overrides were preserved. Follow `sandbox.md` when tool execution fails.
- Gaps and opportunities supported by repository evidence; fixes made; deployment artifact/target/verification/rollback if known; `pending_version` or `applied_version` and why.

Do not infer a requirement for every standard command, force an unsupported toolchain, or add placeholder tests merely to populate a template. A native task runner can replace the example Python runner when that fits the project better. For a repository with no recognized toolchain, install the common agent environment, define a project-specific component and meaningful validation, then finalize only after those checks run successfully. Return a concise summary with chosen tools, demonstrated checks, remaining gaps, and verification.
