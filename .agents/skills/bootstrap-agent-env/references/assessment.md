# Workspace assessment and handoff

For every bootstrap or redeploy, write `.agents/assessment.md` in the target using this structure. Replace examples with observed facts and add project-specific rows. Keep it in the repo so a later agent can explain the decisions and revise them. Where a capability is absent, write `unconfigured` with the evidence or missing input; never mark it passed. A zero-test test runner, echo-only wrapper, empty lint scope, or a build task missing its executable is not validated coverage. Probe the behavior, mark the capability incomplete, and leave the bootstrap version pending until it is meaningful.

| Component | Evidence (files, CI, docs) | Toolchain and version source | Bootstrap | Test | Lint | Format check | Build | Docs | Debug | Deploy plan and verify | Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

Then include these sections:

1. **Enabled tools and agent services.** Record commands and CLI entry points for `doctor`, `bootstrap`, `test`, `lint`, `format-check`, `build`, `validate`, `docs-check`, `debug`, `deploy-plan`, `deploy`, and `verify-deploy`. Identify the installed skills and provider agent definitions. Say which capabilities require human-supplied credentials, target, or tool provisioning. `validate` must include the applicable checks, not just list them.
2. **Coverage gaps and opportunities.** Compare root, nested projects and separate workspace repositories with the actual CI, lockfiles, tools, config, and test directories. Identify missing test scripts, broken tasks, native commands, untracked generated outputs, cache conflicts, and per-variant tasks. Propose improvements based on evidence, and make authorized fixes.
3. **Execution evidence.** Record exact commands attempted, successes/failures, platform, and what could not run. Verify a real failure path propagates nonzero when possible. Record the CI jobs that run the same commands; do not claim CI coverage merely because a sample exists.
4. **Lifecycle.** Note `.agents/bootstrap.json` applied and pending versions, any locally edited files protected from overwrite, the `.local` choice, and decisions about deployment targets and rollback. Keep pending version until validation succeeds.

Return a concise summary to the user with selected tools, capabilities that work, remaining gaps, and verification. Do not treat the detector's proposed commands as proof; inspect the actual project and edit `.agents/commands.json` and scripts accordingly. For a repository with no recognized toolchain, still produce the assessment, add the project-specific adapter, and install the common environment where feasible.
