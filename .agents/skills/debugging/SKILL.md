---
name: debugging
description: Root-cause workflow for bugs, failing tests and CI failures. Use before changing code to fix unexpected behavior.
---

# Debugging

## Order of work

1. Reproduce the failure with a command or a test; if you cannot reproduce it, say so instead of guessing.
2. Read the full error and trace it to the first wrong value or call, not the line that raised.
3. State the cause in one sentence and confirm it with evidence (a log, a failing assertion, a minimal call).
4. Write a failing test that captures the bug (`endurain-backend` `references/testing.md`, `endurain-frontend` `references/docs-and-tests.md`).
5. Fix the cause with the smallest change; do not patch the symptom or widen the change.
6. Run the new test, then the area's tests, then the checks listed in the stack skill.

## Rules

- Change one thing at a time; revert an attempt that did not help before trying the next.
- After two failed fixes, stop and re-read the evidence; the diagnosis is probably wrong.
- Never skip, loosen or delete a test to get green.
- A CI failure is reproduced locally first (same command as the job) before it is fixed.
- Report what was verified and what was not; do not say "fixed" without a passing run.
