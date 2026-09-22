---
name: plan
description: Builds task context, dependency impact, root-cause evidence, and an implementation plan before code changes. Use when the user asks for a plan, when a change touches non-trivial existing code, or as the planning phase of the vibe workflow.
---

# Plan

## Goal

Understand the smallest safe change before implementation.

## Required inputs

- User request.
- Repository instructions such as `AGENTS.md`.
- Existing source/tests/configuration.
- Runtime context/dependency facts when `.vibe/tools/vibe.py` exists.

## Procedure

1. Determine the task mode (`feature`, `change`, `bug_fix`, `refactor`, or `hotfix`) and whether the user requested analysis only or implementation. A planning-only request ends after the plan.
2. Read `.vibe/runtime/current-task.json` when present and only its task artifacts. If the user is continuing the same objective, reuse that task and its original baseline; update its plan as needed. Do not restart merely because a session resumed, verification failed, or the wording changed. Start a task only for a new objective when the runtime is installed:

   ```bash
   python .vibe/tools/vibe.py task start --mode <mode> --request "<short normalized request>"
   ```

3. For a new task, record the initial working tree before implementation:

   ```bash
   git status --short --untracked-files=all
   git diff --name-status
   git diff --cached --name-status
   ```

   Save the initial paths and task-relevant staged/unstaged hunks to the task's `working-tree-before.md`, or in the response when task storage is unavailable. Inspect relevant untracked files separately. Distinguish pre-existing user changes from task edits, including when they share a file. On continuation, read this record without replacing it. If work already began without a record, mark initial ownership as unknown instead of reconstructing it from current code. Without Git, record the known initial file state and review limitation.
4. Build deterministic project facts when the runtime is installed:

   ```bash
   python .vibe/tools/vibe.py context --summary
   python .vibe/tools/vibe.py deps --summary
   python .vibe/tools/vibe.py relevant
   ```

   Create `snapshot before` only if no baseline exists and implementation has not started. An existing `dependency-before.json` is immutable, including during replanning. The runtime preserves valid baselines on repeated calls. If the baseline is missing or invalid after edits began, preserve available evidence and record that before/after dependency comparison is unavailable; never snapshot current edited code as the original baseline.

   Only when those preconditions hold:

   ```bash
   python .vibe/tools/vibe.py snapshot before
   ```
5. If this is a greenfield/new project or the repository has no established architecture:
   - use `architecture-policy.json` as the default design authority,
   - default to `standard + feature-first + modular-layered + framework-native`,
   - keep transport/presentation thin and business behavior in application/domain code,
   - standard projects may use ports/adapters or other abstractions for a concrete boundary, variation, reuse, or testing need; a full Clean/Hexagonal structure is not required.
6. Start from `.vibe/runtime/relevant-context.json`. Read its bounded source/test files, then expand when evidence requires it. If it is empty or unrelated, search filenames and symbols with scoped `rg --files` / `rg`, inspect likely entry points, and rerun `relevant <identified-files>`. An empty result is a retrieval gap, not proof that nothing is affected. Do not paste the full graph into context; summary mode leaves it on disk.
7. Identify:
   - target files/symbols,
   - direct dependencies,
   - reverse dependencies / consumers,
   - bounded transitive impact,
   - related configuration/data/schema/API contracts,
   - framework routes/components affected by the target,
   - active language/framework adapter guidance,
   - effective architecture profile/pattern,
   - clean-code and dependency rules from the architecture policy,
   - related tests,
   - project commands that can verify the change.
8. Run impact analysis for identified targets when the runtime is installed:

   ```bash
   python .vibe/tools/vibe.py impact <target-file> [<target-file> ...]
   ```

9. For a bug:
   - reproduce the symptom using an existing test/command when possible,
   - trace the execution path,
   - identify the root cause from evidence,
   - identify an existing regression test or specify one to add during build.
10. For a change:
   - describe current behavior,
   - describe desired behavior,
   - identify compatibility requirements.
11. For a refactor:
   - record invariants that must remain unchanged,
   - capture baseline tests/behavior before editing.
12. Write the implementation plan to the current task's `plan.md` when task storage is available; otherwise report it in the response. If the runtime is missing, use scoped repository inspection and existing project commands, distinguishing observed facts from inferences. Do not run nonexistent `.vibe` tools or invent runtime artifacts/statuses.

## Plan output

Include:

- mode,
- goal,
- current behavior when relevant,
- desired behavior,
- root cause for bug fixes when established,
- target files/modules,
- dependencies and consumers,
- affected tests,
- compatibility/architecture constraints,
- ordered implementation steps,
- verification commands,
- pre-existing changes and baseline availability,
- acceptance criteria mapped to evidence,
- known uncertainty.

Assign stable criterion IDs, for example `AC1`, and record each observable expected result with the test, command, or manual check that can demonstrate it. Include relevant failure/compatibility cases. Reuse suitable checks; do not add tests for trivial edits when a direct check suffices. Mark any criterion with no feasible check as an explicit evidence gap. Build and verify use these same IDs.

## Persistent-context rules

- `.vibe/state/` is the reusable repository cache across sessions.
- `context` and `deps` must prefer CACHE_HIT, then Git-based INCREMENTAL_REFRESH, and use FULL_REBUILD only when the cache cannot be trusted.
- `.vibe/tasks/` is cold history. Do not enumerate or read old task folders automatically.
- Load an old task only when the user explicitly refers to it or current evidence identifies it as materially relevant.
- Current source/tests/config remain more authoritative than historical task artifacts.
- Respect the configured bounded-context limits; request/read additional files progressively rather than broadening context preemptively.

## Constraints

- Planning must not quietly become implementation.
- Do not claim a root cause without evidence.
- Do not paste the entire dependency graph into context; summarize only the relevant neighborhood.
- If deterministic runtime tooling is unavailable, say which dependency/context facts were inferred manually.
