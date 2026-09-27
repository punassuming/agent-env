# Agent evaluation protocol and 0.3.0 findings

Run independent coding agents on unfamiliar, disposable workspaces. Give each agent only the skill path, target path and a bootstrap request. Inspect the resulting target files and agent summary. Do not substitute a detector unit test for agent behavior. Check each trial against `assessment.md`: the assessment exists; tool selection has observed evidence; runnable validation matches real tests, lint, formatting, docs and build; missing tools or false-positive checks remain pending; CI provisions tools and invokes the same commands; `.local` is ignored; agent skills and provider definitions are installed; deploy requires a known target. Repeat after changing the skill if agents incorrectly declare coverage or hide failures.

Four independent Luna trials in September 2026, using disposable fixtures under `.local/evals/`:

| Workspace | Observed agent behavior | Outcome / refinement |
| --- | --- | --- |
| Python/uv test-only service | Fixed malformed lockfile and project metadata, provisioned pytest and Ruff, wired CI, confirmed one collected test and all checks, finalized 0.3.0. | A valid, evidenced completion. |
| pnpm root plus UI package | Detected both packages and delegated install to root; discovered `node --test` returns success with zero tests and declared lint/build tools were missing. Narrowed validation and left version pending. | Require meaningful test coverage; probe advertised scripts instead of trusting successful exits. |
| Android flavored app | Saw Gradle wrappers only printed text; added static/docs checks and CI, but left actual build/test pending because SDK and genuine build were absent. | An echo-only wrapper is not a build or test; agent must select real variant tasks and SDK provisioning from evidence. |
| Separate Go and Rust repos | Gave each repo its own commands, skills, CI, cache and pending version; created a workspace coordinator. Missing local Go/Rust tools caused visible validation failures. | Make missing toolchains explicit; CI provisioning does not count as a local or remote pass. |

The trials identified a package-level gap too: the installed repository initially received skills and provider copies but not its own manifest and registry manager. The installer now retains both and can discover new child skill folders and provider definitions automatically. Reevaluate on new fixture types when recipes or provider adapters change.
