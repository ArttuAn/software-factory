# Factory workflow

This contract is injected into workers and independent reviewers by the factory.
Repository AGENTS.md and contribution instructions remain authoritative.

1. **Understand.** Read the issue, repository guidance, relevant code and CI. State acceptance criteria and the smallest coherent change. Surface missing requirements before guessing.
2. **Isolate and capture the baseline.** Work only in the assigned isolated worktree/branch. Keep one task per PR. Before editing, run a comparison command for each acceptance criterion and capture the actual output, exit code and baseline commit through the factory proof command. For bugs, reproduce the failure; for new features, demonstrate the missing behavior. Preserve unrelated changes.
3. **Build and prove.** Follow the target repository's architecture and the factory's CODE_STRUCTURE.md guidance. Add meaningful regression coverage. Run the repository's required checks, fix failures, commit the change, and rerun the same comparison commands to capture after evidence. Include screenshots or recordings for visible changes; use comparable measurements or output pairs otherwise. Inspect the evidence yourself and return to building if it does not demonstrate the intended result. Report checks that could not run and why. Do not weaken tests, CI, branch protection, or this contract to get green results.
4. **Publish a draft.** Push the branch and open a draft PR with problem, behavior change, before/after evidence, acceptance criteria, exact commands, commit IDs, and material limitations. Link the issue when one exists. Local artifact paths are not public attachments; use the repository's established upload process. Never merge, deploy, or publish a release.
5. **Independent review.** Request AO's independent reviewer with `ao review trigger <session-id>`. Inspect implementation, tests, architecture and edge cases against the task. Check that proof criteria cover the acceptance criteria, comparisons are meaningful, assertions were not weakened, and media matches its description. Inspect captured proof with the factory proof command. Every review targets a specific PR head SHA. Report real findings through the native review workflow. Never submit an approval on behalf of another reviewer.
6. **Repair.** Address CI failures and review findings in the same session and PR. Rerun relevant validation and after-proof capture, push, and request review of the new head. Stop repeated unproductive attempts and report the blocker.
7. **Handoff.** Ask the factory readiness gate to inspect the PR. Handoff requires named required CI checks to succeed, no failing/pending observed checks, no unresolved review threads, no outstanding change requests, a mergeable open PR, and an independent AO review approved at the current head. A passing gate is evidence for human review, not a merge authorization.

Draft PR creation and the working practices above are agent instructions. The external readiness gate is deterministic and read-only. Enforce merge requirements separately with GitHub branch protection.

Newly connected projects also require captured before/after pairs at handoff.
Existing project policies are not silently migrated. Proof capture verifies
execution and preservation; independent review must judge coverage and meaning.

## Evidence and evaluation

Native conversations, turns, activities and review runs are observed by the factory collector. Preserve tool output and validation evidence; never claim an unavailable result. Orchestrators must record worker delegation using the trace-link command injected into their project configuration. Reviewers must bind every verdict to the actual PR URL and target commit and include concrete findings when requesting changes. Role-probe benchmarks are separate, explicitly labeled sessions and must follow their fixture-specific task rather than publishing a PR.
