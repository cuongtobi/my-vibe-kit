# my-vibe-kit contributor instructions

This repository is the source template for a small cross-agent vibe-coding workflow.

## Principles

- Keep the public workflow small: vibe -> plan -> build -> verify.
- Keep agent instructions portable across Codex, Claude Code, and Antigravity.
- Put reusable methodology in skills and deterministic repository inspection in Python runtime code.
- The kit runtime must remain Python-standard-library-only unless a future change explicitly revises this rule.
- Do not make PASS_VERIFIED possible without runtime evidence.
- Preserve safe installation: never overwrite a conflicting target file unless the user explicitly uses --force.
- Keep AGENTS.md short; detailed procedures belong in on-demand skills.

## Source of truth

1. Runtime behavior and tests.
2. Skill contracts.
3. README usage documentation.
4. Assumptions.

When behavior changes, update tests and both documentation variants (`README.md` and `README_vi.md`) in the same change. Keep their feature/config/CLI coverage equivalent; English is the default README and Vietnamese is the full translated companion.

## Comment and documentation policy

- Prefer self-explanatory code; comments should explain **why**, constraints, invariants, or non-obvious tradeoffs instead of narrating obvious **what**.
- Add concise rationale comments when behavior depends on business rules, compatibility/platform/framework constraints, security assumptions, performance/cache behavior, tricky algorithms, surprising edge cases, or deliberate workarounds.
- Public/shared APIs and non-obvious modules or functions should have concise documentation in the project's native style when it materially helps callers or maintainers understand the contract, side effects, errors, or invariants. Do not add boilerplate docstrings to obvious private helpers.
- Keep TODO/FIXME notes actionable: state the reason, missing condition, or follow-up target instead of leaving vague placeholders.
- When changing code, update or remove nearby comments/docstrings/docs that no longer describe the current behavior.
- Do not add comments merely to increase comment density, repeat names, restate syntax, or explain generated/vendor code the project does not own.

## Verification

Run:

```bash
python -m unittest discover -s tests -v
python -m compileall -q install.py runtime
```

A change is not complete if these checks fail.
