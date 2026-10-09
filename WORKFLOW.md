# Factory workflow

This contract is injected into workers and independent reviewers by the factory.
Repository AGENTS.md and contribution instructions remain authoritative.

1. **Understand.** Read the issue, repository guidance, relevant code and CI. State acceptance criteria and the smallest coherent change. Surface missing requirements before guessing.
2. **Implement.** Work only in the assigned isolated worktree/branch. Keep one task per PR. Add meaningful regression coverage for bugs and behavior changes. Preserve unrelated changes.
3. **Validate.** Run the repository's required checks. Record the exact commands and results. Fix failures. Report checks that could not run and why; never invent successful results. Do not weaken tests, CI, branch protection, or this contract to get green results.
4. **Publish a draft.** Push the branch and open a draft PR with problem, behavior change, validation evidence, and material limitations. Link the issue when one exists. Never merge, deploy, or publish a release.
5. **Independent review.** Request AO's independent reviewer with `ao review trigger <session-id>`. Inspect the implementation, tests and edge cases against the task, not just the summary. Every review targets a specific PR head SHA. Report real findings through the native review workflow. Never submit an approval on behalf of another reviewer.
6. **Repair.** Address CI failures and review findings in the same session and PR. Rerun relevant validation, push, and request review of the new head. Stop repeated unproductive attempts and report the blocker.
7. **Handoff.** Ask the factory readiness gate to inspect the PR. Handoff requires named required CI checks to succeed, no failing/pending observed checks, no unresolved review threads, no outstanding change requests, a mergeable open PR, and an independent AO review approved at the current head. A passing gate is evidence for human review, not a merge authorization.

Draft PR creation and the working practices above are agent instructions. The external readiness gate is deterministic and read-only. Enforce merge requirements separately with GitHub branch protection.

## Evidence and evaluation

Native conversations, turns, activities and review runs are observed by the factory collector. Preserve tool output and validation evidence; never claim an unavailable result. Orchestrators must record worker delegation using the trace-link command injected into their project configuration. Reviewers must bind every verdict to the actual PR URL and target commit and include concrete findings when requesting changes. Role-probe benchmarks are separate, explicitly labeled sessions and must follow their fixture-specific task rather than publishing a PR.
