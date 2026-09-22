---
name: vibe
description: Orchestrates an end-to-end repository change through planning, implementation, and evidence-based verification. Use when the user asks to build a feature, change behavior, fix a bug, perform a refactor, or complete a coding task rather than only analyze it.
---

# Vibe

## Goal

Complete one software change with controlled scope and runtime evidence.

## Procedure

1. Read the repository's durable instructions, especially `AGENTS.md`.
2. Classify the request as one of:
   - `feature`: new externally visible capability.
   - `change`: modify existing behavior or compatibility.
   - `bug_fix`: correct unintended behavior.
   - `refactor`: restructure while preserving behavior.
   - `hotfix`: urgent bug fix where scope must be especially small.
3. Apply the sibling `plan` skill first. If the host cannot invoke sibling skills directly, read `../plan/SKILL.md` and follow it.
4. Do not implement until the plan identifies the target, relevant dependencies, impact, constraints, and verification strategy.
5. Apply the sibling `build` skill.
6. Apply the sibling `verify` skill.
7. If verification fails, return only the failures and necessary evidence to the build procedure. Do not reopen unrelated scope.
8. Finish with a concise summary of:
   - mode,
   - files/areas changed,
   - tests/checks actually run,
   - verification status,
   - any unresolved risk.

## Mode-specific invariants

### bug_fix

Use this sequence:

REPRODUCE -> ROOT CAUSE -> FAILING REGRESSION TEST -> MINIMAL FIX -> PASSING REGRESSION TEST -> AFFECTED TESTS -> VERIFY

If reproduction is impossible, record what was attempted and why before changing code.

### refactor

Capture baseline behavior and a dependency snapshot before editing. Public behavior must remain unchanged unless explicitly requested.

### hotfix

Do not perform opportunistic refactors, package upgrades, renames, or cleanup unrelated to the fault.

## Constraints

- Never silently expand the task.
- Never infer PASS_VERIFIED from code inspection alone.
- Never hide a failed check.
- Prefer deterministic `.vibe/tools/vibe.py` facts over guesses when the runtime is installed.
- Reuse persistent `.vibe/state/` context across sessions; do not rescan or load the whole repository when a valid cache or Git delta is available.
- Treat `.vibe/tasks/` as cold history and never auto-load all prior tasks.
- Keep model context bounded and expand it progressively from `relevant-context.json`.
