# Audit trails, traces, and evaluations

The **Audit & evals** section is part of the local dashboard. Select a role and
agent, expand its events, or include linked roles to follow a whole trace.
The collector runs without a browser, every ten seconds while the supervisor runs.
No external observability service is required.

## Per-role evidence

| Subject | Captured evidence | Evaluation |
| --- | --- | --- |
| Orchestrator | Native session, conversation, turn and tool-activity revisions, usage, reported delegations | Capture coverage, turn/command outcomes, attributed delegation; planning role probe |
| Worker | Native session, isolated branch, conversation, activities, usage, supervisor interventions, saved PR gate outcomes | Capture coverage, turn/command outcomes, saved handoff evidence; external bug-fix assertions |
| Reviewer | Separate `reviewer:<reviewId>` identity, all recorded passes and verdicts, PR URL, target SHA, paginated reviewer conversation | Capture coverage, turn/command outcomes, commit binding and verdict completeness; seeded-defect precision/recall probe |
| CI | Native PR/CI summaries; full GitHub check evidence when a gate is assessed | Success of the most recently captured full check set |
| Gate | Assessment requests, failures, GitHub/AO inputs and saved decisions | Latest saved point-in-time handoff result |
| Supervisor | Dispatch, onboarding, follow-up, interruption, approval decisions, eval requests, native mutation attempts/outcomes, configuration and lifecycle | Journal integrity verification |

Missing data is **unknown**, never a zero-cost claim or successful check. Reported
token usage is cumulative for the native conversation; revised snapshots are not
summed. Costs remain unknown because this build does not apply pricing estimates.
Completed-turn elapsed time is derived only when both native timestamps exist.
An operational failure is a diagnostic, not proof that an engineering task failed:
for example a useful exploratory command can exit unsuccessfully.

## Trace identity and delegation

Events contain a subject ID, capture sequence, UTC observation time, trace root at
capture time, source, actor label, correlation ID when available, payload, previous
hash and current hash. Native timestamps, record IDs, conversation/turn IDs,
revisions, PR URLs and commit SHAs are retained in payloads.

Supervisor intent and native outcome share correlation IDs. A linked trace follows
the current parent graph and includes those correlated factory-side intents,
including events captured before a relationship was reported. Events retain their
original trace root; they are never rewritten to retrofit later knowledge.

Reviewer ownership is taken from native review records. CI and gate records link to
their worker. The native session read API does not always retain a worker's spawn
parent. New factory orchestrator configurations therefore instruct agents to call
`factory.py trace-link <orchestrator-id> <worker-id>` after delegation. The command
checks both native roles and project membership, records the reported link and its
provenance, and rejects reassignment to another parent. It is a report, not proof
of authorship. Same-project membership alone never becomes a delegation edge.
Existing project configurations need the instruction added through native project
configuration; editing WORKFLOW.md does not retrofit running orchestrators.

## Durable journal and export

The journal lives at `<state>/observability/audit.sqlite3`, outside the source repo.
Its directory is private, SQLite uses WAL transactions, and events form an ordered
SHA-256 hash chain. SQLite triggers reject ordinary event UPDATE/DELETE operations.
Observation fingerprints deduplicate unchanged snapshots across restarts while
preserving revisions and a return to an earlier state. Subject metadata changes
are also journaled; the subject index is a mutable convenience projection.

This is **tamper-evident relative to a trusted checkpoint**, not tamper-proof storage.
Someone able to replace the database can recompute a chain or remove its tail.
Export the journal, retain its checkpoint in an independent location, and compare:

```bash
python3 factory.py audit export > /private/path/factory-audit.json
python3 factory.py audit verify
python3 factory.py audit verify --checkpoint /private/path/factory-audit.json
python3 factory.py eval <subject-id>
```

The dashboard has journal verification and JSON download controls. Exports include
the checkpoint, subjects and events. The current export endpoint constructs its
JSON in memory; very large installations should use an external archive pipeline.
There is no automatic deletion or retention policy.

Secret-key fields, common token formats, bearer values, assignment patterns and
private-key blocks are filtered **before** journal persistence. This filtering is
best effort. Arbitrary secrets and proprietary code can remain in tool output;
keep state and exports private. No transcripts are committed or uploaded by this
feature. `local-user`, `system`, and `factory` are source labels, not authenticated
human identities. This local application has no multi-user identity system.

## Evaluations

**Operational evidence v1** runs separately for each subject. The dashboard shows
the current diagnostic. The collector automatically saves a new evaluation whenever its evidence-derived result changes; **Run evidence checks** also saves an explicit versioned result, rubric
hash, evidence and metrics into that subject's audit trail. History remains
inspectable. A previously passing gate is a point-in-time observation, not a claim
that the PR's present head is ready.

**Factory role probes v1** are repeatable live model runs:

* Worker: repair pagination bounds/truncation and empty means; an external Python
  grader checks boundaries and preserved behavior, then discovers and executes
  added unittest regression tests.
* Reviewer: identify three seeded defect categories while preserving a correct
  parity implementation. The grader reports defect-category precision and recall,
  false positives, explanation presence and fixture preservation.
* Orchestrator: return a structured plan with complete file coverage, exclusive
  ownership, known acyclic dependencies, acceptance criteria, and documentation
  ordered after implementation/tests. The fixture must remain unchanged.

Probes run in dedicated **native worker sessions**, labeled with the ability being
tested and linked to a separate benchmark subject. A planning probe does not claim
to exercise native orchestrator delegation; a reviewer probe does not claim to
exercise native PR-review publication. The real production reviewer still gets its
own native review identity, history and operational evaluation.

Each probe has a private Git fixture, a local bare remote (no GitHub publishing),
an isolated native worktree and an external deterministic grader. Results record
the dataset/grader hashes, harness, actual model if exposed, elapsed time, reported
usage, linked execution session, answer and criterion outcomes. Infrastructure
errors, interrupted runs and missing telemetry stay unscored. Malformed agent
answers and failing candidate behavior fail grading. There is one active probe per
supervisor, with a ten-minute agent deadline and interruption on timeout. A restart
marks unfinished probe records interrupted; the linked native session remains
inspectable. Probe fixtures and native sessions are retained for investigation.

These are small, public synthetic tasks. A score is narrow evidence, not a general
software-quality score, security certification or production PR success rate.
Workers run with trusted local permissions, so external graders are not an
adversarial isolation boundary. The full PR/CI/review repair benchmark still needs
a selected target repository and a ground-truth task corpus.

## Capture boundaries

The collector captures every native session exposed by this factory's daemon,
including delegated sessions and role probes, and separately queries durable
reviewer conversations. It pages available history; unsupported interfaces,
missing reviewer IDs, API failures and pagination failures produce coverage errors.
Successfully captured means the available API history was read, not that every
provider tool call or all command output was exposed. Partial-output flags are kept.
History predating the audit journal can be backfilled from native history; its
original timestamps remain distinct from later capture times.

The journal cannot reconstruct transient states between polls, activity lost while
the supervisor was stopped, deleted/unexposed native history, hidden reasoning, or
actions performed outside the supervisor that upstream did not retain. It is not
an OpenTelemetry integration or an OS-wide command recorder.

## HTTP interfaces

Read-only: `/api/observability`, `/api/audit?subject=ID&after=SEQ&limit=100`,
`/api/audit?subject=ID&scope=trace`, `/api/audit/verify`, `/api/audit/export`,
`/api/evals?subject=ID`. Timeline responses carry `nextCursor` and `hasMore`.

Same-origin CSRF-protected POSTs: `/api/evals/run` (`subjectId`),
`/api/benchmarks` (`role`, `harness`), and `/api/trace-links` (`parentId`, `childId`).
Live probes consume the selected coding-agent provider's normal allowance.
