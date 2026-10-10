# Verification

## Video workflow and proof capture - 10 October 2026

- **52 automated tests** passed across `test_factory`, `test_observability` and
  `test_proof`. Real local Git fixtures run a failing baseline command, commit a
  fix, capture the passing comparison and assess it with controlled CI/review
  evidence. Coverage includes CLI argument preservation, stale heads, missing
  pairs, changed commands, later failures, replaced baselines, dirty worktrees,
  wrong branches, timeouts, corrupted/missing media and legacy policy behavior.
- Python compilation, both JavaScript syntax checks and Git whitespace checks
  passed. The CI workflow includes the new suite and module.
- The pinned native daemon and updated supervisor started on separate local
  ports 49082/49080 with empty temporary state. The live supervisor API responded
  successfully. No provider/model jobs were launched for this change.
- Playwright checked the proof inspector at 1440x1100 and 390x844. Both had no
  page overflow, runtime errors or script injection from evidence text. Full-page
  screenshots were visually inspected. Session and proof responses in this UI
  check were explicitly intercepted fixtures; they were not inserted into the
  running factory or presented as real worker results.
- Original English automatic captions were retrieved directly from the supplied
  YouTube video. VIDEO_NOTES.md maps its chapters to the implementation.

The new capture/native-session boundary and successful GitHub gate are tested
with controlled records. A new live agent PR-review/repair cycle was not run.
The local `gh` credential is invalid and needs re-authentication before live
GitHub gate checks can run. Captured output is execution evidence; meaningful
acceptance coverage and media interpretation still require independent review.

## Previous verification - 9 October 2026

## Audit and evaluation extension — verified locally

- **39 automated tests** passed across the factory and observability suites. New coverage includes concurrent ordered journal writes, restart deduplication, returned/revised states, append-only triggers, hash tampering, external-checkpoint tail deletion, linked-trace isolation, paginated worker/reviewer history, missing telemetry, role attribution, probe grading failures and fixture separation from the production board.
- Python compilation, both JavaScript syntax checks and Git whitespace checks passed.
- **Three real Codex role probes passed**: worker bug repair plus externally executed boundary assertions and added regression tests; reviewer detection of all three seeded defect categories with precision/recall 1.0 and no false positives; orchestrator planning with exclusive file ownership, complete coverage and valid dependencies.
- The first live probe exposed a missing remote/default-branch fixture requirement. It remains in the audit as an unscored infrastructure error. The fixture now uses a local bare remote; no GitHub repository or PR is created for probes.
- A supervisor/native-daemon restart preserved all three successful probe results, the failed setup attempt, linked execution sessions, captured activities and automatically saved per-subject evaluation records.
- A real journal export containing 192 events was independently checked by recomputing every SHA-256 link, sequence and checkpoint. CLI verification against the retained external export checkpoint also passed.
- Browser accessibility/DOM inspection confirmed role selection, token-usage display, explicit unknown model/cost fields, saving an evidence evaluation, launching role probes, actual graded outcomes and journal verification. The 309px layout reported no horizontal overflow. Screenshot capture timed out in the in-app browser, so no new visual screenshot is claimed. Secret transcripts and runtime databases remain outside Git.

These are synthetic ability probes executed by native worker sessions. They do **not** establish production PR success rates, exercise native orchestrator delegation end to end, or substitute for a real native PR-review lifecycle. The production-reviewer collector boundary is tested with controlled native API records. The original production PR/CI/repair limitations below still apply.

## Original baseline verification

- **20 extension tests**, including parameterized failure cases: missing required checks, failed/pending/skipped/neutral checks, unresolved threads, stale approvals, another PR's approval, superseding review passes, change requests without branch protection, changing heads, full evidence pagination, retry identifiers, failed onboarding, supervisor Host/Origin/CSRF checks, and safe vector-asset routing.
- Python compilation and JavaScript syntax checks.
- Official release package and bundled daemon SHA-256 checks recorded in UPSTREAM.json. Upstream source is unmodified at the pinned commit.
- Real upstream project creation with factory workflow, Codex worker/reviewer configuration, auto-review and feedback injection.
- **Real Codex execution:** browser-dispatched session `factory-live-fixture-1`, branch `ao/factory-live-fixture-1/root`, isolated native worktree under the private state directory. It read the disposable repository's README and returned `# Factory integration fixture`. No PR was requested or created in this smoke test.
- Graceful supervisor/daemon restart, recovery of the same session and its three stored messages, completed turn and actual provider response.
- Browser onboarding, invalid-path error visibility, dispatch, board facts, conversation history and review controls. No browser warning/error logs were present at final inspection. The screenshot uses the app panel's actual narrow viewport.
- Branded interface: both logo images loaded; the page fit its 309px viewport without horizontal overflow. New agent/role tags, status labels and icon controls were checked against the existing real session. All seven SVG assets, 18 icon symbols and 14 GitHub label definitions validated locally. No generated bitmap or asset service is required.
- Real GitHub query and negative gate probe against [upstream PR #6472](https://github.com/OrchestratorInc/agent-orchestrator/pull/6472). At the observed head `57883512c5e640399afe1dee261297fa646d4efe`, five checks succeeded. The factory correctly rejected handoff because its selected test worker had no approved current-head AO review. This upstream PR was only read; it was not modified or claimed as factory output. A copy of the actual assessment is in `evidence/blocked-gate.json`.

## Scope of the validation

No target production repository or issue was supplied. Real PR creation, native independent PR-review execution and the full CI/review repair loop remain to be exercised on the selected repository. The wrapper's readiness rules are tested with controlled evidence and a real negative probe; a successful production handoff has not been claimed.

The upstream Go/Electron application was not modified or rebuilt, and its complete Go/Electron test matrix was not run. This build uses the pinned official release binary. Multi-worker orchestrator delegation, alternative harnesses, automatic tracker intake and full desktop-only interfaces were not exercised here.

There is one real local smoke-test project on the live board. No simulated workers or successful PRs were added to the interface. Runtime state and credentials are excluded from the deliverable archive.
