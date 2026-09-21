# Project agent instructions

## Product / system

Describe the project in 2-5 sentences. Keep this file durable and concise.

## Architecture invariants

- Preserve existing module boundaries unless the task explicitly changes architecture.
- Do not silently change public APIs, persisted schemas, or external contracts.
- Prefer existing abstractions and dependencies over introducing parallel ones.

## Coding rules

- Make the smallest correct change.
- Do not perform unrelated cleanup during feature or bug work.
- Every bug fix should add a regression test when practical.
- Never weaken or delete a valid test merely to make verification pass.
- Do not add a dependency without checking whether the repository already provides equivalent capability.

## Vibe workflow

For non-trivial code changes use:

PLAN -> BUILD -> VERIFY

Use the installed vibe/plan/build/verify skills. Dependency and context facts should come from `.vibe/tools/vibe.py` when available.

## Definition of done

A change is complete only when:
- requested behavior is implemented,
- relevant tests exist or are updated,
- dependency/architecture impact was checked,
- configured verification commands pass,
- the final diff contains no unexplained unrelated changes.

Do not claim PASS_VERIFIED without runtime evidence.

## Project commands

Customize these for this repository, and keep `.vibe/config.json` in sync.

- install: TODO
- test: TODO
- lint: TODO
- typecheck: TODO
- build: TODO
