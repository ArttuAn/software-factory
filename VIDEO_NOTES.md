# Applied Video Lessons

Source: [Greg Isenberg with Ras Mic, Building a Software Factory that actually works](https://www.youtube.com/watch?v=_LCeJZFIsd4).
Reviewed the original English automatic captions on 10 October 2026.

| Video chapter | Lesson | Application here |
| --- | --- | --- |
| [05:23](https://www.youtube.com/watch?v=_LCeJZFIsd4&t=323s) | Give each task its own worktree. | Native AO already isolates workers. AGENTS.md clarifies default-branch starts and continued tasks. Isolation still requires integration conflict handling. |
| [11:34](https://www.youtube.com/watch?v=_LCeJZFIsd4&t=694s) | Make code readable to people and future agents. | CODE_STRUCTURE.md adds focused design guidance that respects the target repository. |
| [14:48](https://www.youtube.com/watch?v=_LCeJZFIsd4&t=888s) | Show before/after behavior, visually or with measured output. | PROOF.md and the proof command capture process evidence, commit identity and optional preserved media. New projects require these pairs at handoff. |
| [22:25](https://www.youtube.com/watch?v=_LCeJZFIsd4&t=1345s) | Feed independent review findings back through implementation and proof. | Existing AO review/repair handles this without a new paid service. WORKFLOW.md now requires proof again after repairs. |
| [29:21](https://www.youtube.com/watch?v=_LCeJZFIsd4&t=1761s) | Keep the workflow portable across models and tools. | Instructions remain Markdown; capture and grading are standard-library Python. The execution adapter still uses the existing pinned AO runtime. |

The video uses Greptile's score as its review signal. This implementation retains
the evidence already present in this repository: a current-head AO
verdict, CI, resolved review discussions and a human merge decision. It does not
claim an AO approval is a Greptile score. No new external account is required.
