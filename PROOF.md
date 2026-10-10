# Before and After Proof

This evidence contract is independent of the tools used to capture it. Use
repository tests, terminal logs, browser recordings, benchmarks, or a compatible
collector. No factory application, provider account, or particular review
service is required. Do not invent execution results or treat an agent's
narrative as captured process output.

## Capture

Before editing, record the baseline for every acceptance criterion. For each
comparison retain:

- A stable criterion and the behavior it tests.
- The baseline and after commit IDs, branch/worktree, and relevant environment.
- The exact command, inputs, expected exit status, actual exit status and output.
- Inspected media or measurements where useful, with preservation locations.
- Capture failures, output truncation, unavailable checks and other limitations.

Use committed, clean snapshots, including untracked files. Keep evidence outside
the source worktree so capture itself does not dirty it. For a new feature, an
inline assertion can report its absence without altering the baseline tree.
Use the same command and comparable inputs on both commits; record any necessary
environment differences. Preserve a failing baseline's actual nonzero exit code.
After must succeed. The baseline must be an ancestor of the after commit.

Capture fresh after evidence whenever the implementation changes. A failed
recapture supersedes an earlier success. Replacing a baseline requires a fresh
after comparison. Evidence must identify the exact PR head handed to review.
Do not put credentials or private data in logs or public PR attachments.

## Visual and Performance Evidence

For visible changes, run browser assertions and retain before/after screenshots
or recordings. Inspect the media and preserve both versions rather than
overwriting the baseline. A content hash establishes preservation, not whether
an image actually depicts the claimed behavior.

For performance work, run the same benchmark with the same inputs and comparable
environment on both commits. Record sample counts, measurements, units and the
agreed threshold. Two arbitrary numbers do not establish an improvement. Review
test and benchmark changes independently for weakened assertions.

Embed or link criteria, commands, output/media pairs, commit IDs and limitations
in the draft PR through the repository's established upload process. Local
artifact paths alone are not accessible PR evidence.

## Review

The independent reviewer must verify that criteria cover the task, assertions
exercise real behavior, comparisons are meaningful, media matches its
description, and after evidence belongs to the current head. Review the actual
implementation as well as its proof. Report missing or failed evidence as a
handoff blocker; no capture tool alone guarantees correctness.

Optional runtime adapters may enforce additional capture formats and checks.
Their reports must distinguish machine-checked facts from reviewer judgment.
Humans retain the final merge decision.
