---
name: verify
description: Verifies a code change using dependency snapshots, configured runtime checks, tests, and final diff review. Use before declaring any vibe-coded task complete, when reviewing a fix, or when the user asks whether a change is safe or finished.
---

# Verify

## Goal

Produce evidence that the change satisfies the request without introducing unexplained dependency or behavior regressions.

## Procedure

1. Read the plan/impact record and `AGENTS.md`.
2. Rebuild deterministic repository facts when the runtime exists:

   ```bash
   python .vibe/tools/vibe.py context
   python .vibe/tools/vibe.py architecture
   python .vibe/tools/vibe.py deps
   python .vibe/tools/vibe.py snapshot after
   ```

3. Compare dependency state:
   - added edges,
   - removed edges,
   - new cycles,
   - unexpected consumers.
4. Run:

   ```bash
   python .vibe/tools/vibe.py verify
   ```

5. Review the diff against the effective architecture policy:
   - new code remains feature-first where practical,
   - standard projects do not introduce unnecessary Clean/Hexagonal ceremony,
   - strict projects keep framework/infrastructure dependencies at the edges,
   - controllers/routes/handlers stay thin,
   - new abstractions are justified rather than speculative,
   - modules remain cohesive and avoid new circular coupling.
6. Inspect the final `git diff` semantically:
   - requested behavior is present,
   - no unrelated change,
   - no accidental public contract change,
   - error/edge states are handled,
   - tests genuinely exercise the changed behavior.
7. For bug fixes, verify:
   - original reproduction no longer fails,
   - regression test passes,
   - nearby behavior still passes.
8. For refactors, verify baseline behavior still passes.
9. Report the runtime status exactly.

## Status rules

- `PASS_VERIFIED`: only when required runtime checks actually ran and passed.
- `FAIL_VERIFICATION`: one or more required checks failed or a forbidden new dependency cycle appeared.
- `NEEDS_VERIFICATION_CONFIG`: the project requires verification commands but none are configured.

Never translate `NEEDS_VERIFICATION_CONFIG` into success.

## Constraints

- Never delete/disable a failing test simply to pass.
- Never omit a failed command from the final report.
- Never claim runtime evidence that was not actually produced.
