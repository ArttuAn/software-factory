# Agent Orchestrator Adapter

This adapter implements the portable contract using the pinned AO runtime.
The supervisor supports Codex, Claude Code, Copilot, and OpenCode. It does not
pin a model in project onboarding; model selection and availability come from
the selected authenticated agent CLI and native runtime configuration. This
does not imply support for every model, harness, or platform.

## Execution and Review

Work in the assigned native worker's isolated branch/worktree. The native daemon
owns session execution, lifecycle, and repair delivery. Delegate through AO
workers and avoid overlapping file ownership. Limit active workers to three;
this is an instruction, not an enforced daemon quota.

Request independent review with `ao review trigger <session-id>`. Every review
must target the actual PR URL and head SHA. Use the native review workflow for
findings; never invent review records or approval. The factory's read-only gate
requires a current-head independent AO approval, successful configured and
observed checks, resolved discussions, no outstanding change requests, and an
open mergeable PR. It accepts draft PRs and never merges or undrafts them.
In this adapter, publish drafts only; never merge, deploy, or publish a release.

New projects require captured proof as well. Existing projects retain their
policy until deliberately reconfigured. Use the AO-specific PROOF.md capture
instructions and injected absolute commands. Updated Markdown is not automatically
injected into running sessions or previously connected projects.

## Audit and Evaluation

The collector observes native conversations, turns, activities and review runs.
Record orchestrator-to-worker delegation with the injected trace-link command;
this records a reported relationship validated against native roles/project.
Preserve validation output and distinguish unavailable telemetry from zero.
Role probes are labeled synthetic sessions, not production PR success rates;
follow their fixture task instead of publishing a PR.

This is trusted local execution, not an untrusted-code sandbox. The loopback
supervisor and native API must not be exposed through public tunnels. Merge
restrictions require GitHub branch protection and appropriate permissions.
