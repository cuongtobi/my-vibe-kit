---
name: vibe
description: Orchestrates an end-to-end repository change through planning, implementation, and evidence-based verification. Use when the user asks to build a feature, change behavior, fix a bug, perform a refactor, or complete a coding task rather than only analyze it.
---

# Vibe

## Goal

Complete one software change with controlled scope and runtime evidence.

## Behavioral orchestration

- Convert the request into observable goals before implementation; a non-trivial step should have a corresponding check or evidence source.
- Surface materially consequential assumptions early. Do not interrupt autonomous execution for minor, reversible ambiguity that can be handled with a stated conservative assumption.
- Prefer the simplest scoped solution that satisfies the acceptance criteria; complexity must be justified by an actual constraint, boundary, or verified need.
- Keep retries evidence-driven: diagnose -> change -> re-check. Do not churn through rewrites without new evidence.

## Procedure

1. Read the repository's durable instructions, especially `AGENTS.md`.
2. Classify the request as one of:
   - `feature`: new externally visible capability.
   - `change`: modify existing behavior or compatibility.
   - `bug_fix`: correct unintended behavior.
   - `refactor`: restructure while preserving behavior.
   - `hotfix`: urgent bug fix where scope must be especially small.
3. Apply the sibling `plan` skill first. If the host cannot invoke sibling skills directly, read `../plan/SKILL.md` and follow it. Read the current task before creating one; continue the same objective in place and preserve its original baselines.
4. Do not implement until the plan identifies targets, dependencies, impact, constraints, acceptance criteria, and their verification evidence. The plan must also classify whether the task is security-sensitive and, when it is, identify the relevant security surfaces and required evidence. A request to implement authorizes this workflow within its scope without a second plan approval. A planning-only request ends after plan; honor explicit user approval boundaries and ask only for missing decisions that materially affect the outcome.
5. Apply the sibling `build` skill.
6. Apply the sibling `verify` skill. A security-sensitive task is not complete merely because normal runtime checks pass; its explicit security evidence must also be complete.
7. When the runtime exists, require the structured completion gate after verification/evidence recording:

   ```bash
   python .vibe/tools/vibe.py complete --summary
   ```

   Only `COMPLETE` authorizes reporting the workflow as finished. Keep `PASS_VERIFIED` as the narrower runtime-check status for compatibility.
8. Route gaps and failures by cause using the table below. Keep the existing task and baseline during retries; do not reopen unrelated scope.
9. Finish with a concise summary of:
   - mode,
   - files/areas changed,
   - tests/checks actually run,
   - verification status,
   - acceptance criteria met, unmet, or unverified,
   - any unresolved risk.

## Recovery routing

| Situation | Next action |
| --- | --- |
| A check exposes a code defect or new cycle | Return the failure and evidence to build, then verify the fix. |
| The target or acceptance criteria are wrong/incomplete | Update plan and impact within the same task, preserving baselines; clarify only a material unresolved decision. |
| `NEEDS_VERIFICATION_CONFIG` | Identify established project check commands; configure them within the authorized scope, then verify. Do not substitute a no-op command or edit application code to bypass this status. |
| A command cannot run because of the environment | Diagnose the specific missing tool/configuration; resolve it within scope or report the blocker and next required action. |
| Runtime is absent | Use scoped inspection and the project's own checks; distinguish manual evidence from runtime verification and do not invent a runtime status. |
| Relevant context is low-confidence, fallback-truncated, empty, or unrelated | Inspect `retrieval_confidence`, fallback evidence, and indexed matches; then use a bounded project-native search for dynamic/framework relationships, identify explicit targets, and rerun relevant/impact when available. |
| A baseline is missing or invalid after implementation began | Preserve available evidence and report the unavailable comparison. Never manufacture a pre-change baseline from current code. Restore one only from authentic pre-change evidence. |
| Security-sensitive evidence is missing, incomplete, or contradicted by the diff | Return to plan/build as appropriate, identify the affected trust boundary, add the required targeted checks, and rerun verification. Do not downgrade the task to non-sensitive merely to complete it. |

Retry when a concrete diagnosis or change justifies another attempt. If the same blocker remains and no new evidence or authorized remedy is available, report what was attempted and what is needed; do not cycle through build/verify without progress.

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
- Keep model context bounded and expand it progressively from `relevant-context.json`; never treat low-confidence retrieval or a truncated fallback as evidence that no other file is affected.
- Treat the built-in dependency graph as advisory static evidence; native analyzers/tests remain authoritative for runtime/framework behavior.
