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

1. Determine the task mode: `feature`, `change`, `bug_fix`, `refactor`, or `hotfix`.
2. Start a task record when the runtime is installed:

   ```bash
   python .vibe/tools/vibe.py task start --mode <mode> --request "<short normalized request>"
   ```

3. Build deterministic project facts:

   ```bash
   python .vibe/tools/vibe.py context
   python .vibe/tools/vibe.py deps
   python .vibe/tools/vibe.py relevant
   python .vibe/tools/vibe.py snapshot before
   ```

4. If this is a greenfield/new project or the repository has no established architecture:
   - use `architecture-policy.json` as the default design authority,
   - default to `standard + feature-first + modular-layered + framework-native`,
   - keep transport/presentation thin and business behavior in application/domain code,
   - do not introduce Clean/Hexagonal ports/adapters unless the effective profile is `strict`.
5. Start from `.vibe/runtime/relevant-context.json`. Read only the bounded source/test files it identifies, then expand selectively when evidence requires it. Do not load the full repository or full dependency graph into model context.
6. Identify:
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
7. Run impact analysis:

   ```bash
   python .vibe/tools/vibe.py impact <target-file> [<target-file> ...]
   ```

8. For a bug:
   - reproduce the symptom using an existing test/command when possible,
   - trace the execution path,
   - identify the root cause from evidence,
   - specify the regression test to add during build.
9. For a change:
   - describe current behavior,
   - describe desired behavior,
   - identify compatibility requirements.
10. For a refactor:
   - record invariants that must remain unchanged,
   - capture baseline tests/behavior before editing.
11. Write the implementation plan to the current task's `plan.md` when task storage is available.

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
- known uncertainty.

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
