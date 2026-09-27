# Evaluate this registry's skills and agent instructions

A trial measures the *agent plus instructions plus environment*. Keep the agent/model version, tool permissions, host toolchains, caches, fixture starting commit and prompt comparable across runs. Changing two at once prevents causal attribution. Start with the observed errors in `evaluation.md`; promote each meaningful failure to a committed fixture and an assertion. The fixture contains only project evidence and `EVAL_ENV.md`; keep grading criteria outside the agent's target repo. The agent must not see expected answers or the prior agent's trace.

## Prepare and run

```bash
EVAL=.agents/skills/bootstrap-agent-env/scripts/evaluations/loop.py
python "$EVAL" prepare --suite controlled --source . --output .local/eval-A
python "$EVAL" prepare --suite controlled --source /path/to/other/revision --output .local/eval-B
# To compare repository instruction files, add --agents-file /path/to/versioned/AGENTS.md to each prepare.
```

Suites: `controlled` (Python/Node/mixed/split), `web` (FastAPI and pnpm/React permutations), `stacks` (Android, Go, Rust, C#, Django, static site, Docker/Compose/Kubernetes/Helm), and `frameworks` (Django/Angular monorepo, Express/React Router npm workspaces, Sails/React Router sibling Git repositories). `--variant none` removes the skill pointer for a no-skill comparison; a source revision from another checkout tests a changed skill. To evaluate an AGENTS.md instruction change, pass `--agents-file` with the appropriate version to each run. The tool commits those instructions into each fixture before the agent starts and labels them as fixture input in the report; the repository's own source AGENTS.md is **not** automatically applied to another project. In either case the agent must receive *only* the generated `run_manifest.json` prompt for its case and `EVAL_ENV.md`. Do not show it `eval-run.json`, grader code, prior fixes, or grading results. The target checkout is disposable, but the source skill path must remain readable. Each run has a fresh target; never replay against a mutated checkout.

Invoke an independently configured agent CLI when one exists. The harness cannot configure or guarantee its sandbox/network policy. Review the executable, provider approval mode and target before enabling command execution. Example for a CLI that accepts a prompt filename (adapt exact argv to the installed CLI):

```bash
python "$EVAL" invoke --run .local/eval-A --case python-library \
  --agent example --model pinned-id --dry-run \
  --command agent-cli --workspace '{target}' --prompt-file '{prompt_file}'
python "$EVAL" invoke --run .local/eval-A --case python-library \
  --agent example --model pinned-id \
  --command agent-cli --workspace '{target}' --prompt-file '{prompt_file}'
```

`invoke` passes the prompt on stdin too; it uses argv arrays, no shell expansion. It captures exit status, duration, stdout and stderr under ignored `.local/`. No CLI is included in this package, and no agent provider is assumed. An exit code of zero from an agent only means its process ended successfully. Inspect traces and diff for hidden installs, wrong paths, calls outside the target, placeholder commands, zero tests, and unwanted deployment. Sanitize logs before sharing them: raw traces may contain secrets.

For subagent or manually launched trials, save the actual trace and check results, then record them:

```json
[
  {"id": "validate", "argv": ["./scripts/agent-env.sh", "validate", "--all"], "exit_code": 1},
  {"id": "unit-tests", "argv": ["python", "-m", "unittest", "discover", "-s", "tests"], "exit_code": 0, "test_count": 1, "log": "/path/to/unittest-output.txt"}
]
```

```bash
python "$EVAL" record --run .local/eval-A --case python-library \
  --agent codex --model pinned-id --trace /path/to/trace.txt --checks /path/to/checks.json
python "$EVAL" grade --run .local/eval-A > .local/eval-A/grade-output.json
python "$EVAL" grade --run .local/eval-B > .local/eval-B/grade-output.json
python "$EVAL" compare --before .local/eval-A/grade.json --after .local/eval-B/grade.json
```

The grader performs no project commands. It checks the assessment, instructions, installed skill, CI file, ignored cache, expected component paths, and whether existing release artifacts have candidate checks. It flags a finalized fresh checkout with no recorded successful broad validation, and marks CI execution **unverified**. These are structural proxies: a registered command can be a no-op; a passed exit code need not mean any tests were collected. Review command argv, test counts, CI logs, deployment scope, and the agent's reasoning before accepting a result. Use human review for ambiguous release intent and whether coverage is meaningful. An agent's written claim is not an execution receipt.

Read `grading.md` before claiming that a skill change helped. `score --run RUN --review REVIEW.json` requires a separate evidence-backed review on six dimensions and applies objective ceilings and critical failure gates. `compare-scores --baseline OLD_1/score.json ... --candidate NEW_1/score.json ...` compares paired repeats by fixture, model, host and reviewer. A single clean run remains insufficient evidence of improvement; grading rejects a changed source after fixture preparation.

## Improvement loop

1. Establish a baseline from the current revision and at least one clean run per relevant case. For variable outcomes, repeat cases with the same model/settings and report counts; one run does not estimate reliability.
2. Identify a failure with file diffs, trace and command receipts. Fix the *smallest responsible instruction, recipe, template, or runner*. Do not add language to the global skill for a one-off repo detail; keep local adaptations in the repo.
3. Prepare fresh candidate fixtures from the changed source revision. Run the same cases and model/permissions/host; compare per-case failures and new regressions. Test an unrelated case too, to detect an overfit instruction.
4. Review false positives in the grader and correct them with an explicit fixture before treating it as a gate. Keep a human review decision with the report until meaningful command execution and CI evidence exist.
5. Commit the new regression fixture and improvement in this registry. CI should run fixture-generation/grader unit tests on every change. Real agent trials need an explicitly provisioned agent runner and credentials; schedule them or trigger on relevant skill/AGENTS changes, then publish a report. Never pretend deterministic CI tests are live agent evaluations.

OpenAI's [skill evaluation guide](https://developers.openai.com/blog/eval-skills) recommends prompt, captured run, checks, and comparable results; its [agent evaluation guidance](https://developers.openai.com/api/docs/guides/agent-evals) separates traces from repeatable datasets. Claude's [evaluation guidance](https://platform.claude.com/docs/en/test-and-evaluate/develop-tests) recommends specific success criteria and code or human grading where appropriate. This repository uses a provider-independent file format so that source-controlled instructions and fixture diffs remain inspectable.
