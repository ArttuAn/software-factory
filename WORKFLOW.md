# Factory Workflow

This is the portable delivery contract. It does not require a particular model,
coding-agent harness, orchestrator, dashboard, or review service. The target
repository's instructions and contribution policy remain authoritative. Choose
tools and models through the harness you use; judge their output by evidence,
not by a provider name or a model's self-assessment.

1. **Understand.** Read the task, repository guidance, relevant code and CI. State acceptance criteria and the smallest coherent change. Surface missing requirements before guessing.
2. **Isolate and capture the baseline.** Use a dedicated branch/worktree for each independent task, starting from the current remote default branch. Continue an existing task on its assigned branch. Keep one task per PR and preserve unrelated changes. Before editing, record a comparison for each acceptance criterion: command, inputs, actual output, exit status, and baseline commit. For bugs reproduce the failure; for features demonstrate the missing behavior.
3. **Build and prove.** Follow the target repository's architecture and the build guidelines. Add meaningful regression coverage. Run required checks, fix failures, commit, and repeat the same comparisons against the new commit. Include inspected screenshots or recordings for visible changes; use comparable measurements or output pairs otherwise. Follow the proof contract. Report checks that could not run and why. Do not weaken tests, CI, repository protections, or acceptance criteria to get green results.
4. **Publish a draft.** Push the task branch and open a draft PR with the problem, behavior change, acceptance criteria, before/after evidence, exact commands, commit IDs, and material limitations. Link the issue when one exists. Local artifact paths are not public attachments; use the repository's established upload process. Never merge, deploy, or publish a release without explicit human authorization.
5. **Independent review.** Obtain review in a separate reviewer context through the chosen tools. The reviewer must inspect the actual diff, tests, architecture, edge cases, and proof against the task, not merely repeat the implementer's summary. Check acceptance coverage, meaningful comparisons, unchanged assertions, and media descriptions. Bind every verdict to the PR and exact head commit. Never submit an approval on behalf of another reviewer. A different model is optional; an independent review context is required.
6. **Repair.** Address CI failures and review findings in the same task branch and PR. Rerun validation and after-proof, push, and obtain review of the new head. Old approval and old after-proof do not approve a new commit. Stop repeated unproductive attempts and report the blocker.
7. **Handoff.** Verify that named required CI checks succeed, no observed checks are failing or pending, review discussions and change requests are resolved, the open PR is mergeable, proof covers the task at the current head, and an independent reviewer approves that head. State remaining limitations. Humans decide whether to merge, deploy, or release.

## Tool Boundaries

These instructions are not a sandbox, a concurrency quota, or branch protection.
Use repository permissions and required checks for enforceable merge policy.
Automated evidence gates are optional implementations of this contract; report
what was actually checked and never claim an unavailable result. A passing gate
is evidence for human review, not merge authorization.

When delegating, assign explicit ownership and acceptance criteria. Avoid
overlapping edits and retain task-to-worker relationships in the chosen tool's
history. Worktrees isolate edits, not integration conflicts. Apply any runtime
limits from the selected adapter separately.
