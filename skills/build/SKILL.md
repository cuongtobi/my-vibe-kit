---
name: build
description: Implements the current planned code change with minimal scope and appropriate tests. Use after planning when the user wants code modified, including feature implementation, behavior changes, bug fixes, refactors, and hotfixes.
---

# Build

## Goal

Implement the approved plan with the smallest correct diff.

## Before editing

1. Read `AGENTS.md`.
2. Read the current task plan and impact data when present under `.vibe/tasks/` or `.vibe/runtime/`.
3. Confirm the target scope and constraints.
4. If new evidence changes the scope materially, update impact analysis before editing outside the plan.

## Implementation rules

- Prefer existing project patterns and dependencies.
- Do not create duplicate abstractions because they are easier for the agent.
- Do not add a package until existing capabilities were checked.
- Do not silently modify public APIs, persisted schemas, wire formats, permissions, or configuration compatibility.
- Avoid unrelated formatting/refactors.
- Keep changes reviewable.

## Mode behavior

### feature

Implement acceptance behavior and add focused tests.

### change

Implement desired behavior and preserve declared compatibility. Update old tests only when the intended contract changed.

### bug_fix

1. Add or identify a regression test that demonstrates the bug.
2. Run it and confirm it fails for the expected reason.
3. Apply the smallest root-cause fix.
4. Run the regression test and confirm it passes.
5. Run affected tests.

Never weaken a valid test to make the fix appear successful.

### refactor

Run the baseline tests before changing structure. Preserve behavior and public contracts. Avoid mixing feature work into the refactor.

### hotfix

Patch only what is needed to remove the fault. Defer cleanup.

## After editing

- Inspect `git diff`.
- Check for unexpected files.
- Run the most focused tests available.
- Hand off to the verify skill; implementation is not proof of completion.
