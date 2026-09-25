# Project agent instructions

## Product / system

Describe the project in 2-5 sentences. Keep this file durable and concise.

## Architecture invariants

- For a new project, default to feature-first + modular layered architecture + framework-native conventions.
- For an existing project, preserve existing module boundaries unless the task explicitly changes architecture.
- Default new-project profile is `standard`; only use Clean/Hexagonal structure when the effective architecture profile is `strict`.
- Prefer framework conventions over generic architecture ceremony.
- Dependencies should move from presentation/transport toward application/business/data boundaries, never from lower-level infrastructure back into controllers/UI.
- Keep cross-feature dependencies on public services/contracts rather than importing another feature's internals.
- Do not silently change public APIs, persisted schemas, or external contracts.
- Prefer existing abstractions and dependencies over introducing parallel ones.

## Behavioral coding policy

Use these rules to reduce common LLM coding mistakes without blocking reasonable autonomy:

- **Think before coding.** State material assumptions and tradeoffs. If ambiguity can change behavior, public contracts, data, security, compatibility, or task scope, ask before choosing silently. If ambiguity is minor, reversible, and low-risk, state the assumption and proceed conservatively.
- **Simplicity first.** Implement the minimum code required for the accepted behavior. Do not add speculative features, single-use abstractions, or configurability that was not requested. Add defensive handling only for states that are plausible under established contracts; do not invent impossible failure modes.
- **Surgical changes.** Touch only what the task, its tests, compatibility/security requirements, or cleanup caused by the task actually require. Do not refactor, reformat, rename, or remove unrelated existing code. Match the repository's established style unless the task explicitly changes it.
- **Goal-driven execution.** Turn the request into observable acceptance criteria and map implementation steps to checks. For bugs, reproduce the failure when practical, fix the root cause, and verify the regression. For refactors, establish behavior before and after the structural change.
- **Changed-line traceability.** Every changed line should trace to the user request, an acceptance criterion, a required regression/compatibility/security check, or cleanup made necessary by this change.
- **Progress without churn.** Retry only when new evidence or a concrete change justifies another attempt. Do not repeatedly rewrite working code merely to make it look more sophisticated.

## Coding rules

- Use intent-revealing names and keep functions/modules focused.
- Prefer guard clauses when they reduce deep nesting.
- Keep controllers/routes/handlers thin; keep non-trivial business logic out of transport/UI code.
- Avoid god services, circular dependencies, hidden global mutable state, and swallowed errors.
- Do not add interfaces/repositories/wrappers without a concrete boundary, variation, reuse, or testing reason.
- Keep configuration/secrets outside business logic.
- Test behavior and important edge cases; comments should explain why, not narrate obvious code.
- Prefer simple code over clever code.
- Make the smallest correct change.
- Do not perform unrelated cleanup during feature or bug work.
- Every bug fix should add a regression test when practical.
- Never weaken or delete a valid test merely to make verification pass.
- Do not add a dependency without checking whether the repository already provides equivalent capability.

## Vibe workflow

For non-trivial code changes use:

PLAN -> BUILD -> VERIFY

Use the installed vibe/plan/build/verify skills. Dependency, context, and architecture-policy facts should come from `.vibe/tools/vibe.py` when available.

## Context rules

- Reuse persistent context/dependency state from `.vibe/state/` across sessions.
- Prefer Git-based incremental refresh over full repository rescans.
- Start from `.vibe/runtime/relevant-context.json` and read additional source only when evidence requires it.
- Respect the configured source/test/module context limits.
- Treat `.vibe/tasks/` as cold history. Never auto-load every old task; read a prior task only when explicitly referenced or materially relevant.
- Cached/indexed does not mean verified. Only runtime verification commands can establish `PASS_VERIFIED`.
- Read retrieval `selection_diagnostics` when scope is non-obvious; dependency/reverse-dependency expansion is advisory static evidence.
- Treat `.vibe/runtime/security-candidates.json` as advisory evidence only. The agent makes the final security classification and records it explicitly.

## Definition of done

A change is complete only when:
- requested behavior is implemented,
- relevant tests exist or are updated,
- dependency/architecture impact was checked,
- configured verification commands pass,
- all structured acceptance criteria are marked `met`,
- a final security decision/evidence record is present,
- `python .vibe/tools/vibe.py complete --summary` reports `COMPLETE`,
- the final diff contains no unexplained unrelated changes.

`PASS_VERIFIED` is the narrower runtime-check status and is not, by itself, workflow completion. Do not claim either status without its runtime evidence.

## Project commands

Customize these for this repository, and keep `.vibe/config.json` in sync.

- install: TODO
- test: TODO
- lint: TODO
- typecheck: TODO
- build: TODO
