---
name: verify
description: Verifies a code change using dependency snapshots, configured runtime checks, tests, and final diff review. Use before declaring any vibe-coded task complete, when reviewing a fix, or when the user asks whether a change is safe or finished.
---

# Verify

## Goal

Produce evidence that the change satisfies the request without introducing unexplained dependency or behavior regressions.

## Procedure

1. Read `AGENTS.md`, the current plan/impact record, its acceptance criteria, and `working-tree-before.md` when available. Verify the current task rather than starting another. If no plan exists, derive explicit criteria from the user's request and record any uncertainty.
2. Refresh deterministic repository facts when the runtime exists. The runtime should reuse persistent state or apply a Git delta when possible; a full rebuild is a fallback, not the default:

   ```bash
   python .vibe/tools/vibe.py context --summary
   python .vibe/tools/vibe.py deps --summary
   ```

3. Take `snapshot after` and compare dependency state only when the current task has a valid pre-implementation `dependency-before.json`:

   ```bash
   python .vibe/tools/vibe.py snapshot after
   ```

   Read the relevant entries in the resulting `dependency-diff.json`:
   - added edges,
   - removed edges,
   - new cycles,
   - unexpected consumers.

   The built-in graph is explicitly `static-best-effort` and advisory. A clean graph is not evidence that dynamic imports, DI bindings, generated routes/code, Rails/WordPress runtime registration, macros, or other framework magic are unaffected; use project-native tests/analyzers or direct checks for those paths when relevant.

   Without that baseline, report the missing comparison and inspect current dependencies as far as possible. Do not create a late `snapshot before`, overwrite an invalid baseline, or treat an empty graph as the original state. The runtime refuses invalid/missing-baseline snapshot comparisons.
4. When the runtime is installed, run:

   ```bash
   python .vibe/tools/vibe.py verify --summary
   ```

   Read relevant command results and dependency differences from `verification.json`, especially on failure; the summary intentionally omits logs and graph details. A false `dependency_comparison_available` must be reported as a limitation. If the runtime is unavailable or cannot run, execute the project's established checks directly, report actual commands/results, and state that runtime verification is unavailable without inventing a runtime status.

   Runtime verification refreshes the final dependency snapshot after commands run. If `rerun_required` is true, review command-produced changes and rerun every command in `rerun_commands` through runtime verification until inputs are stable; do not substitute the earlier snapshot or command results. Evidence must match the current `task_id` and `source_fingerprint`; `status.verification_current` identifies stale reports but does not establish success.

5. Review the diff against the effective architecture policy:
   - new code remains feature-first where practical,
   - standard projects do not introduce unnecessary Clean/Hexagonal ceremony,
   - strict projects keep framework/infrastructure dependencies at the edges,
   - controllers/routes/handlers stay thin,
   - new abstractions are justified rather than speculative,
   - modules remain cohesive and avoid new circular coupling.
6. Inspect unstaged changes (`git diff`), staged changes (`git diff --cached`), and relevant untracked files listed by `git status --short --untracked-files=all`. Compare with the initial working-tree record; preserve and identify pre-existing changes. Review the task's changes semantically:
   - requested behavior is present,
   - no unrelated change,
   - no accidental public contract change,
   - error/edge states are handled,
   - tests genuinely exercise the changed behavior,
   - non-obvious decisions, invariants, workarounds, security assumptions, and performance/cache constraints have rationale where maintainers would otherwise be likely to misread them,
   - comments do not merely narrate obvious code or duplicate names/syntax,
   - public/shared contracts and non-obvious modules/functions have useful documentation when callers or maintainers need it,
   - touched comments, docstrings, and nearby documentation still match current behavior,
   - TODO/FIXME notes introduced or touched by the change are actionable and specific.
7. For bug fixes, verify:
   - original reproduction no longer fails,
   - regression test passes,
   - nearby behavior still passes.
8. For refactors, verify baseline behavior still passes.
9. Map every acceptance criterion to actual evidence in `acceptance.md` in the current task, or in the response when task storage is unavailable:

   | Criterion ID | Expected result | Command/test/manual evidence | Result and limitations |
   | --- | --- | --- | --- |
   | AC1 | Observable behavior from the plan | Actual check and its observed outcome | met / unmet / unverified, with any gap |

   Report the runtime status exactly and the acceptance results separately. Passing configured commands does not establish that every requested behavior was tested. An unmet/unverified required criterion or missing required comparison keeps the task incomplete even if runtime checks pass.
10. Evidence must correspond to the final changes. If review leads to further code, test, or configuration edits, rerun the affected checks and runtime verification, then update the acceptance evidence. Documentation-only edits require the relevant document checks.

## Status rules

- `PASS_VERIFIED`: only when required runtime checks actually ran and passed.
- `FAIL_VERIFICATION`: one or more required checks failed, a forbidden new dependency cycle appeared, or verification inputs changed and require a stable rerun.
- `NEEDS_VERIFICATION_CONFIG`: no verification commands are configured, even when `verification.require_commands` is `false`. At least one command must actually run and pass before reporting `PASS_VERIFIED`.

Never translate `NEEDS_VERIFICATION_CONFIG` into success.

## Context constraints

- Verify the current task and current diff; do not load unrelated historical task folders.
- Cache reuse is an optimization only. Verification status still comes from commands that actually ran.
- Static dependency evidence narrows review scope but never replaces runtime/framework verification.
- A CACHE_HIT never implies PASS_VERIFIED.

## Constraints

- Never delete/disable a failing test simply to pass.
- Never omit a failed command from the final report.
- Never claim runtime evidence that was not actually produced.
- For missing verification configuration, identify established project checks and configure them only within the authorized scope. Never add a no-op command to obtain a passing status. Route code failures to build, scope errors to plan, and environment/configuration failures to their actual cause.
