# Build Guidelines

Follow the target repository's existing architecture and contribution guidance.
Keep transport parsing, business decisions and external integrations separable.
Keep tool-specific execution details outside the portable delivery contract.

Prefer small functions with explicit inputs and results. Keep deterministic
decisions independent of I/O so they can be tested against real failure cases.
Reuse existing helpers; remove duplication introduced by the change. Add a new
layer only when it improves a concrete boundary. A service layer is useful for
shared business rules, but it is not a reason to restructure an unrelated app.

Review readability as well as behavior: names, ownership, error handling, dead
code, and edge cases. Do not weaken validation to make a change pass review.
