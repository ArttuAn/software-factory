# Open-source factory research

Inspected GitHub repositories, current READMEs, architecture documents, release artifacts and relevant source on **9 October 2026**. Six separate GitHub repository searches covered software factories, coding-agent orchestration, worktrees, autonomous development and SWE agents. This is a relevant shortlist, not an exhaustive or objective ranking. Stars indicate reach; they do not measure PR quality.

DeepAPI's requested skill and local installation were absent, so repository research used the connected GitHub API directly.

| Project | Stars observed | License | What it actually supplies | Fit for this factory |
|---|---:|---|---|---|
| [OpenHands](https://github.com/OpenHands/OpenHands) | 90,361 | MIT | Agent Canvas control center, ACP agents and multiple execution backends | Strong general platform; broader deployment and runtime scope |
| [MetaGPT](https://github.com/FoundationAgents/MetaGPT) | 70,788 | MIT | Role-based multi-agent software development | Useful role decomposition; less directly matched to persistent PR operations |
| [GPT Pilot](https://github.com/Pythagora-io/gpt-pilot) | 33,653 | Check upstream terms | Application-generation system | More focused on building applications than operating a PR production loop |
| [Symphony](https://github.com/openai/symphony) | 27,608 | Apache-2.0 | Tracker-driven service specification and experimental Elixir reference implementation | Strong model for reconciliation, retained workspaces, retries and a versioned workflow |
| [Ralph](https://github.com/snarktank/ralph) | 21,935 | MIT | Iterative agent loop driven by task/PRD files | Useful small-loop pattern; not a complete supervisor |
| [SWE-agent](https://github.com/SWE-agent/SWE-agent) | 20,513 | MIT | Repository issue-solving agent | Strong execution specialist rather than a multi-session factory |
| [Agent Orchestrator](https://github.com/OrchestratorInc/agent-orchestrator) | 12,984 | Apache-2.0 | Native daemon, worktree isolation, durable sessions, orchestrators, independent review and CI/review reactions | **Selected foundation:** best direct fit for this computer's existing Codex and GitHub tools |
| [Open SWE](https://github.com/langchain-ai/open-swe) | 10,827 | MIT | LangGraph/DeepAgents coding workflow with persistent sandbox execution and PR feedback | Strong durable execution model; current deployment adds Python 3.14, sandbox/model setup and Agent Server deployment requirements |
| [mini-SWE-agent](https://github.com/SWE-agent/mini-swe-agent) | 8,339 | MIT | Minimal, inspectable issue-solving harness | Good reference for a simple worker, not a factory control plane |
| [Attractor](https://github.com/strongdm/attractor) | 1,328 | Apache-2.0 | Specifications for graph-driven agent workflows, coding agents and LLM clients | Useful explicit gates and retry semantics; the repository is specifications, not a ready-to-run factory |
| [Fusion](https://github.com/Runfusion/Fusion) | 1,261 | MIT | Direct software-factory product with graph workflows and role lanes | Relevant alternative; current beta is a broader runtime/platform |

## Decision

Use the actual [Agent Orchestrator v0.13.5 release](https://github.com/OrchestratorInc/agent-orchestrator/releases/tag/v0.13.5), pinned to commit `c95ae361eee48d33c2f443c6d2fe69c445f548a8`. Its [architecture](https://github.com/OrchestratorInc/agent-orchestrator/blob/v0.13.5/docs/architecture.md) puts lifecycle ownership in a durable daemon and keeps clients thin. Its [review implementation](https://github.com/OrchestratorInc/agent-orchestrator/blob/v0.13.5/backend/internal/domain/review.go) records each review's target commit. Its native lifecycle feeds CI failures and review findings back into workers, with persisted feedback signatures and bounded repeated nudges.

The bundled daemon and unmodified source are upstream software. The factory adds a thin HTTP supervisor, onboarding configuration, a workflow contract and a stricter read-only handoff gate. It does not recreate the execution engine or use upstream's browser-preview fixtures as live agent data.

Patterns adopted from [Symphony's specification](https://github.com/openai/symphony/blob/main/SPEC.md): explicit workflow instructions, retained workspaces, persistent session ownership and observable operational state. This is **not** a Symphony-compatible implementation; its Linear tracker service and full workflow front matter are not implemented here.

Pattern adopted from [Attractor's specification](https://github.com/strongdm/attractor/blob/main/attractor-spec.md): a successful agent narrative does not satisfy an external completion gate. This build evaluates concrete current-head evidence. It does **not** implement Attractor's DOT engine or claim specification compliance.

## What “quality” means here

Workers receive a concrete implement → validate → draft PR → independent review → repair → handoff contract. The gate checks named CI contexts, all observed CI contexts, unresolved threads, GitHub change requests, mergeability and AO review results at the current commit. It rejects unknown or missing evidence and rechecks the head before returning a report.

Passing those checks does not prove that requirements or tests are sufficient. Human review and repository branch protection still govern merging. Worker concurrency, draft creation and no-merge behavior are agent instructions, not hard sandbox restrictions. Upstream handles the lifecycle; this extension supplies a point-in-time readiness assessment.
