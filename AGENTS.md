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

## Behavioral coding policy

Use these rules to reduce common LLM coding mistakes without blocking reasonable autonomy:

- **Think before coding.** State material assumptions and tradeoffs. If ambiguity can change behavior, public contracts, data, security, compatibility, or task scope, ask before choosing silently. If ambiguity is minor, reversible, and low-risk, state the assumption and proceed conservatively.
- **Simplicity first.** Implement the minimum code required for the accepted behavior. Do not add speculative features, single-use abstractions, or configurability that was not requested. Add defensive handling only for states that are plausible under established contracts; do not invent impossible failure modes.
- **Surgical changes.** Touch only what the task, its tests, compatibility/security requirements, or cleanup caused by the task actually require. Do not refactor, reformat, rename, or remove unrelated existing code. Match the repository's established style unless the task explicitly changes it.
- **Goal-driven execution.** Turn the request into observable acceptance criteria and map implementation steps to checks. For bugs, reproduce the failure when practical, fix the root cause, and verify the regression. For refactors, establish behavior before and after the structural change.
- **Changed-line traceability.** Every changed line should trace to the user request, an acceptance criterion, a required regression/compatibility/security check, or cleanup made necessary by this change.
- **Progress without churn.** Retry only when new evidence or a concrete change justifies another attempt. Do not repeatedly rewrite working code merely to make it look more sophisticated.

## Comment and documentation policy

- Prefer self-explanatory code; comments should explain **why**, constraints, invariants, or non-obvious tradeoffs instead of narrating obvious **what**.
- Add concise rationale comments when behavior depends on business rules, compatibility/platform/framework constraints, security assumptions, performance/cache behavior, tricky algorithms, surprising edge cases, or deliberate workarounds.
- Public/shared APIs and non-obvious modules or functions should have concise documentation in the project's native style when it materially helps callers or maintainers understand the contract, side effects, errors, or invariants. Do not add boilerplate docstrings to obvious private helpers.
- Keep TODO/FIXME notes actionable: state the reason, missing condition, or follow-up target instead of leaving vague placeholders.
- When changing code, update or remove nearby comments/docstrings/docs that no longer describe the current behavior.
- Do not add comments merely to increase comment density, repeat names, restate syntax, or explain generated/vendor code the project does not own.

## Security policy

The kit does not guarantee that generated or modified code is secure. Its security goal is narrower and auditable: **security-sensitive changes cannot silently pass without explicit security review and evidence**.

Treat a task as security-sensitive when it touches authentication, authorization, sessions, tokens, passwords, file upload or filesystem access, database queries using user-controlled data, user-controlled URLs, HTML rendering, command/process execution, payments, secrets/credentials, or another trust boundary with comparable impact.

For security-sensitive work:

- Plan identifies the security-sensitive surfaces, trust boundaries, abuse/failure cases, and evidence required to verify them.
- Build preserves existing controls, uses framework-native secure defaults, least privilege, explicit validation/encoding, safe secret handling, and avoids inventing cryptography or bypassing protections for convenience.
- Verify performs an explicit security diff review, runs targeted security tests, and uses established project-native security/dependency scanners when available and relevant.
- Missing scanner/tooling is reported as a limitation; generic tests, lint, or `PASS_VERIFIED` alone are not proof of security.
- Never weaken authentication, authorization, validation, isolation, secret handling, or another security control merely to make a failing test/check pass.

## Runtime contracts and completion

- Versioned runtime artifacts are validated against `schemas/contracts-v1.json`. Invalid/stale contract versions must be rebuilt or rejected rather than trusted.
- `PASS_VERIFIED` is intentionally limited to configured runtime commands/dependency checks. It is not the final workflow status.
- A task is complete only when the runtime completion gate reports `COMPLETE` from current verification evidence, all acceptance criteria marked `met`, and an explicit final security decision/evidence record.
- The runtime security classifier is advisory. Agents must make the final classification; overriding detected candidate surfaces as non-sensitive requires a recorded rationale.
- Architecture auto-strict decisions should use the relevant task/module scope when explicit targets are available instead of promoting an entire large monorepo by size alone.

## Verification

Run:

```bash
python -m unittest discover -s tests -v
python -m compileall -q install.py runtime
```

A change is not complete if these checks fail.
