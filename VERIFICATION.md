# Verification — 9 October 2026

## Passed locally

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
