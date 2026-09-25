---
name: build
description: Implements the current planned code change with minimal scope and appropriate tests. Use after planning when the user wants code modified, including feature implementation, behavior changes, bug fixes, refactors, and hotfixes.
---

# Build

## Goal

Implement the user's requested change within the planned scope with the smallest correct diff.

An implementation request authorizes proceeding through plan, build, and verify within that scope; a separate approval of the plan is not required. Respect an explicit planning-only request or user-requested approval boundary. Ask only for a missing decision that materially affects behavior, compatibility, or scope, and continue independent work when possible.

## Before editing

1. Read `AGENTS.md`.
2. Read `.vibe/runtime/current-task.json` and only that task's plan/impact artifacts when present. Reuse the current task for a continuation; do not reset its dependency or working-tree baseline. If the plan is missing or materially outdated, apply the plan procedure within the existing authorization before editing. Do not scan historical task folders.
3. Read `.vibe/runtime/relevant-context.json` when available and use its indexed retrieval evidence plus bounded source/test scope as the initial working set; otherwise start from the plan's identified files and project-native inspection.
4. Read `.vibe/runtime/architecture-policy.json` when present.
5. Check the target scope, acceptance criteria, and `working-tree-before.md` against the user's request. Preserve pre-existing staged, unstaged, and untracked work, including unrelated hunks in a target file. Do not reset, stage, or discard user changes to simplify the diff.
6. If new evidence changes the scope materially, update impact analysis before editing outside the plan.

## Behavioral implementation policy

- Implement the minimum code that satisfies the accepted behavior and constraints. Do not add speculative features, future-proofing layers, or configurability that is not required by the task.
- Prefer an existing direct pattern over a new abstraction when the abstraction has only one current use and no concrete boundary/variation/testing need.
- Add defensive/error handling for plausible states under established contracts. Do not create branches for states that are provably impossible solely to appear defensive.
- Make surgical changes: do not refactor, rename, reformat, comment-clean, or delete unrelated existing code. If unrelated dead/problematic code is discovered, report it instead of folding it into the patch.
- Clean up imports, variables, helpers, tests, or files made obsolete by **this change**; do not treat pre-existing cleanup as implicitly authorized.
- Match established project style even when another style would also be reasonable.
- Every changed line should be explainable by the request, an acceptance criterion, a regression test, a compatibility/security requirement, or cleanup made necessary by this patch. If it cannot be traced to one of those, remove it or explicitly re-plan the scope.
- If implementation grows substantially beyond the planned shape, revisit the plan before continuing rather than normalizing the extra complexity after the fact.

## Architecture and clean-code rules

For greenfield/new modules, follow the effective architecture policy:

- Default: feature-first + modular layered + framework-native conventions.
- Standard dependency direction: presentation/transport -> application/service -> domain/data boundary.
- Keep controllers/routes/handlers thin.
- Keep non-trivial business logic out of transport/UI and framework glue.
- Prefer feature/module cohesion over one global folder per technical layer.
- Use repositories, interfaces, ports, adapters, and extra abstraction only when a real boundary/variation/testing need justifies them.
- If the effective profile is `strict`, use the policy's Clean/Hexagonal inward dependency rules and keep framework/infrastructure at the edges.
- Apply the clean-code rules in `architecture-policy.json`: intent-revealing names, focused functions/modules, low nesting, explicit errors/dependencies, no hidden global mutable state, behavior-focused tests, and simple code over clever code.

## Comment and documentation policy

Apply comments and documentation selectively as part of implementation quality:

- Prefer code that explains itself through names and structure. Do not narrate obvious statements, assignments, branches, or function calls.
- Add a concise **why** comment when a future maintainer could otherwise misread a non-obvious decision, invariant, tradeoff, workaround, compatibility constraint, security assumption, performance/cache behavior, or surprising edge case.
- Document public/shared APIs and non-obvious modules/functions in the project's native documentation style when callers need to know contracts, inputs/outputs, errors, side effects, lifecycle, or invariants. Avoid boilerplate docstrings for obvious private helpers.
- Preserve useful existing rationale comments. If the implementation changes the behavior they describe, update or remove them in the same change.
- TODO/FIXME comments must be actionable and specific. Do not leave vague notes such as `TODO: fix later`.
- Do not comment generated/vendor code unless the project owns and intentionally maintains that code.
- Follow the repository's existing comment/docstring conventions when they are compatible with these rules.

## Security policy

If the plan marks the task security-sensitive, or implementation reveals a security-sensitive surface the plan missed, stop treating security as implicit: update the plan/criteria as needed and apply the relevant secure-coding controls.

General rules:

- Preserve authentication, authorization, validation, isolation, and secret-handling controls unless the requested behavior explicitly changes them and the plan records that contract.
- Prefer framework-native security mechanisms and safe defaults over custom security code.
- Validate at trust boundaries, encode/escape at the output sink, use least privilege, and fail closed where access-control decisions are involved.
- Never hardcode, expose, or log secrets, credentials, raw passwords, access/refresh tokens, session identifiers, private keys, or payment credentials.
- Do not invent cryptography, password hashing, token formats, or random-token generation when established, reviewed primitives already exist.
- Avoid shell/process execution with user-controlled strings; use structured arguments and existing safe APIs. Avoid dynamically constructing database queries from untrusted input when parameterized/native query APIs are available.
- Do not disable or weaken CSRF, XSS/output encoding, SSRF/network restrictions, authorization checks, TLS/certificate checks, cookie protections, upload restrictions, or similar controls merely to make the implementation easier.
- Add focused negative/abuse-case tests for the security properties changed by the task when they can be exercised at the project's normal test boundary.

Surface-specific review prompts are requirements to assess when applicable, not a claim that every item applies to every task:

- **Authentication/session/token/password:** authorization boundary, token/session rotation and expiry, revocation, replay, fixation, cookie flags, credential storage, brute-force/rate-limit behavior when in scope, and sensitive logging.
- **File upload/filesystem:** size limits, MIME/extension handling, path traversal, filename normalization/sanitization, overwrite behavior, executable content, storage boundary, symlink behavior when relevant, and authorization.
- **Database/user-controlled query data:** parameterization, injection, unsafe dynamic identifiers, mass assignment, tenant/row ownership, transaction/integrity boundaries, and least-privilege data access.
- **User-controlled URL/network fetch:** scheme/host restrictions, redirects, private/internal network reachability, credential forwarding, DNS/redirect SSRF behavior when relevant, and response-size/time limits.
- **HTML/template/rendering:** contextual output encoding, unsafe HTML bypasses, script/URL injection, template injection, and applicable CSRF/CSP behavior.
- **Command/process execution:** shell avoidance, argument separation, executable selection, environment inheritance, path handling, working directory, and privilege boundary.
- **Payments/webhooks:** server-side amount/currency authority, idempotency, authorization, webhook/signature verification, replay handling, state transitions, and secret logging/storage.
- **Secrets/credentials:** source-control exposure, logs/errors/telemetry, storage, rotation/revocation path, least privilege, and accidental client-side exposure.

## Implementation rules

- Prefer existing project patterns and dependencies.
- Do not create duplicate abstractions because they are easier for the agent.
- Do not add a package until existing capabilities were checked.
- Do not silently modify public APIs, persisted schemas, wire formats, permissions, or configuration compatibility.
- Avoid unrelated formatting/refactors.
- Keep changes reviewable.
- Implement the plan's observable acceptance criteria and maintain their evidence mapping. If a requirement changes, update the plan and affected checks rather than silently dropping the criterion.
- Expand beyond the bounded relevant-context file set only when a concrete dependency, consumer, failing test, dynamic/framework relationship, or contract requires it.
- Treat the runtime dependency graph as a static advisory baseline, not proof that no additional runtime dependency exists.
- Never read all historical `.vibe/tasks/` as background context.

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

- Inspect `git diff`, `git diff --cached`, and `git status --short --untracked-files=all`; read relevant untracked files separately. Compare against the initial working-tree record so pre-existing changes are not attributed to this task.
- Run the most focused tests available.
- Hand off to the verify skill; implementation is not proof of completion.
- Code, test, or configuration changes after verification invalidate evidence for affected criteria. Rerun the affected checks and final runtime verification before reporting completion. For documentation-only edits, rerun the relevant document checks without repeating unrelated tests.
