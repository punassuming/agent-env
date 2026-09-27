# Workspace assessment and handoff

For every bootstrap or redeploy, write `.agents/assessment.md` in the target. Use a compact table, sections, or another readable structure that fits the project. Include these facts, with evidence rather than a fixed set of columns:

- Components and boundaries: root packages, workspaces, independent repos, and the files/CI that identify them.
- Selected toolchain and version source; existing native commands; skills and agent definitions deployed; the reason for each added command.
- Actual available entry points for relevant capabilities. For each selected check, connect observed requirement or artifact → native command and prerequisite → observed result → exact coverage claim. Mark relevant missing capabilities `unconfigured` with a reason, and omit irrelevant categories or mark them `not applicable`. Add project-specific capabilities when evidence requires them; the common command names are examples, not a required checklist.
- What `validate` runs, what CI provisions, commands and exit status observed locally, failures, and what was not exercised. Separate application, container build, Compose, rendered manifest/chart and live deployment coverage when those artifacts exist. A zero-test test runner, echo-only wrapper, empty lint scope, or build task missing its executable is incomplete coverage even if a command exits zero.
- Sandbox observations: writable roots, tool/cache/temp locations and network or permission blocks; the selected ignored local root and whether any existing overrides were preserved. Follow `sandbox.md` when tool execution fails.
- Gaps and opportunities supported by repository evidence; fixes made; deployment artifact/target/verification/rollback if known; `pending_version` or `applied_version` and why.

Do not infer a requirement for every standard command, force an unsupported toolchain, or add placeholder tests merely to populate a template. A native task runner can replace the example Python runner when that fits the project better. A repository with no recognized toolchain still needs an evidence-based component and meaningful validation; propose a minimal check only when it tests something the repository actually needs, and keep an unsatisfied capability pending. Return a concise summary with chosen tools, demonstrated checks, remaining gaps, and verification.
