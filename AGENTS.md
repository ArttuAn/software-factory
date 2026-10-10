# Factory Development

Read WORKFLOW.md for the delivery contract, CODE_STRUCTURE.md before implementation,
and PROOF.md before capturing acceptance evidence.

Start independent features in separate worktrees from the target repository's
current remote default branch. Continue an existing task on its assigned branch.
Do not discard local work or reset a branch. Worktrees isolate edits; overlapping
changes can still cause integration conflicts and need coordination.

For changes to this repository, run the checks in .github/workflows/factory.yml.
Keep the three core Markdown documents and workflow.py independent of runtime
adapters. AO-specific execution instructions belong in adapters/ao; the optional
AO supervisor leaves execution and lifecycle ownership in the pinned daemon.
Keep final merge, deployment and release decisions with the user.
