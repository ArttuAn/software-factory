# Before and After Proof

Newly connected projects require captured before/after proof as well as the
existing CI and independent-review gate. Existing policies retain their prior
behavior; `proofRequired` in a gate report makes this explicit. Re-onboard a
project deliberately to adopt the new contract, rather than overwriting a live
project configuration.

## Capture

Run these commands from the factory checkout, using the worker's native session
ID and isolated worktree. Capture the baseline before editing. Both snapshots
must be committed and clean, including untracked files. The same comparison
command must work against both versions. For a new feature, an inline assertion
can report its absence on the baseline without changing the baseline tree.

```bash
python3 factory.py proof capture app-1 --workspace /path/to/worker \
  --phase before --criterion 'Empty input returns None' --expect-exit 1 \
  -- python3 -c 'from sample import mean; assert mean([]) is None'

# Implement, validate and commit the fix in the worker worktree.
python3 factory.py proof capture app-1 --workspace /path/to/worker \
  --phase after --criterion 'Empty input returns None' \
  -- python3 -c 'from sample import mean; assert mean([]) is None'

python3 factory.py proof show app-1 --head FULL_PR_HEAD_SHA
python3 factory.py gate app-1 https://github.com/owner/repo/pull/123
```

The default expected exit code is zero. Use the observed nonzero exit code for
a reproduced bug's baseline. After must expect zero. Capture every acceptance
criterion with its own stable description. A new after capture supersedes the
earlier one, including when the latest check fails. A new baseline requires a
fresh after capture. Code changes after proof require fresh after proof.

Commands run directly with an argument list, in the verified native worker's
branch, with a 120-second default timeout (`--timeout` accepts 1-600 seconds).
Pipes and shell expansion are not implicit. Timeouts kill the command process
group. Commands that change the commit or leave the tree dirty fail capture.
Do not put credentials in arguments or output. Logs receive the audit journal's
best-effort secret filtering; the first 64 KiB is retained, with truncation
marked. Output and exit status are captured from the process, not accepted from
an agent's narrative.

## Visual and Performance Evidence

Use a browser test that asserts the expected behavior and writes its screenshot
or recording outside the worktree. Add `--artifact /path/to/capture.png` to each
capture. PNG, JPG, WebP, MP4 and WebM are accepted, up to 25 MiB each. Each file
is copied into private runtime state by content hash, so overwriting the source
does not destroy the baseline. Attachments are operator-supplied; hashes prove
preservation, not that the media depicts the asserted behavior. Review the media.

For performance work, run the same benchmark with the same inputs on both
commits. The command should print sample counts, measurements and units and
exit nonzero when the agreed threshold fails. The factory preserves the output;
it does not infer a speed improvement from two arbitrary numbers. Changes to
benchmark or test code must be assessed independently for weakened assertions.

Embed before/after media or output pairs, criteria, commands, commit IDs and
material limitations in the draft PR. The review inspector displays recorded
evidence; local artifact links are for local inspection and are not public PR
attachments. Upload artifacts through the repository's established process.

## Handoff

The gate checks each recorded criterion for matching commands, successful
expected exits, a verified ancestor baseline, an after capture at the PR head,
and intact output and attachments. A failed or missing pair blocks new projects.

Captures are scoped to the worker. The independent reviewer must verify that
the criteria cover the task, the assertions test the real behavior, screenshots
match their descriptions, and measurements are comparable. A passing capture
is execution evidence, not a guarantee of correctness. The existing audit-chain
and trusted-local-execution limitations still apply. Review runs must still
approve the actual PR head. Humans decide whether to merge.
