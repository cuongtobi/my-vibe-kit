# my-vibe-kit

[Tiếng Việt](README_vi.md)

A small, personal **vibe-coding skills kit** for working on real repositories with Codex, Claude Code, and Google Antigravity.

The kit intentionally keeps the agent surface small:

- `vibe` — orchestrates the full change.
- `plan` — builds bounded context, dependency/impact analysis, and a change plan.
- `build` — implements only the approved scope.
- `verify` — proves the change with runtime evidence.

The same four skills are materialized into each agent's native project layout by `install.py`, so there is one source of truth instead of separate copies for each agent.

## Quick start

Clone the kit:

```bash
git clone https://github.com/cuongtobi/my-vibe-kit.git
cd my-vibe-kit
```

Install it into a project:

```bash
python install.py --target /path/to/your-project --agents codex claude antigravity
```

Windows PowerShell:

```powershell
python .\install.py --target C:\code\your-project --agents codex claude antigravity
```

Preview without writing:

```bash
python install.py --target /path/to/your-project --agents all --dry-run
```

Then open the target project with Codex, Claude Code, or Antigravity and use the workflow normally:

```text
Use vibe to add CSV export to the report.
```

```text
Use vibe to fix the crash when backtest history is empty.
```

```text
Use plan to analyze replacing SQLite with PostgreSQL. Do not edit code yet.
```

Main workflow:

```text
vibe
  -> plan: persistent context + dependency + impact + plan
  -> build: code + tests
  -> verify: dependency diff + lint/type/test/build + diff review
```

For bugs:

```text
REPRODUCE
-> ROOT CAUSE
-> FAILING REGRESSION TEST
-> MINIMAL FIX
-> PASSING REGRESSION TEST
-> AFFECTED TESTS
-> VERIFY
```

If the target project has no reliable test/lint/typecheck/build command configured, edit `.vibe/config.json`. The kit returns `NEEDS_VERIFICATION_CONFIG` instead of pretending the project is verified.

## Design goals

- One personal workflow across Codex, Claude Code, and Antigravity.
- Works with project-local filesystem skills and CLI/IDE agent workflows.
- File-based context instead of relying on chat history.
- Persistent JSON context/dependency cache across sessions.
- Git-aware incremental refresh instead of rescanning the whole repository for every task.
- Bounded relevant-context retrieval before model reasoning.
- Explicit modes: `feature`, `change`, `bug_fix`, `refactor`, `hotfix`.
- Minimal-change implementation by default.
- Runtime evidence before completion.
- Standard-library-only Python runtime for the kit itself.
- Optional integration with stronger ecosystem tooling when a project already uses it.

## Supported languages and frameworks

The workflow is language-agnostic. The runtime adds stack-aware adapters and baseline dependency scanners.

| Language | Baseline dependency scan | Framework adapters |
| --- | --- | --- |
| Python | AST import graph | Flask, FastAPI, Django |
| JavaScript | relative import/require graph | Express, React, Vue, Nuxt, Svelte, SvelteKit, Vite, Next.js |
| TypeScript | relative import graph | Express, NestJS, React, Vue, Nuxt, Svelte, SvelteKit, Vite, Next.js |
| PHP | namespace/use + literal require/include graph | Laravel, WordPress |
| Java/Kotlin | package/import graph | Spring |
| Go | module-local import graph | Gin, Fiber |
| Rust | mod + `crate::use` graph | Actix Web |
| Other | project/file map | generic fallback |

Framework adapters add route/component/controller/model/provider context and framework-specific verification guidance. Frontend adapters understand components, hooks/composables/stores, file-system routes, and server/client boundaries. The WordPress CMS adapter understands plugins, themes, hooks/filters/shortcodes, REST routes, blocks, templates, and WordPress integration boundaries.

The runtime resolves:

```text
detected language
       +
detected framework(s)
       ↓
active-adapter.json
       ↓
plan / impact / build / verify
```

The four core skills therefore do not need separate Flask/Laravel/React/WordPress/etc. variants.

For frontend stacks, adapters are composable. A TypeScript + React + Vite project can activate all three relevant layers; a Next.js project can activate Next.js plus React, while architecture guidance prioritizes the meta-framework. Likewise Nuxt is prioritized over Vue and SvelteKit over Svelte. Vite remains a tooling adapter rather than the source of application architecture.

## Architecture policy

For greenfield projects, the default policy is:

```text
feature-first
+
modular layered architecture
+
framework-native conventions
+
Clean Code rules
```

The default effective profile is `standard`:

```text
presentation / route / controller
            ↓
application / service
            ↓
domain / business rules
            ↓
repository / data / infrastructure boundary
```

This is guidance, not a requirement to create every layer in every feature. Repositories, interfaces, ports, wrappers, factories, and adapters are added only when a real boundary, variation, reuse, or testing need justifies them.

The kit switches to Clean/Hexagonal-style inward dependency rules only when:

- `architecture.profile` is explicitly set to `strict`, or
- `profile=auto` and the project crosses the configured strict thresholds.

Default architecture configuration:

```json
{
  "architecture": {
    "profile": "auto",
    "default_profile": "standard",
    "module_style": "feature-first",
    "default_pattern": "modular-layered",
    "strict_pattern": "hexagonal",
    "framework_conventions": "prefer",
    "allow_auto_strict": true,
    "strict_thresholds": {
      "source_files": 300,
      "feature_roots": 20
    }
  }
}
```

Force strict mode:

```json
{
  "architecture": {
    "profile": "strict"
  }
}
```

Strict dependency direction:

```text
presentation
    ↓
application / use-cases
    ↓
domain
    ↑
ports
    ↑
infrastructure adapters
```

Framework conventions still win over generic architecture ceremony. Laravel stays Laravel-native, Django stays app-oriented, NestJS stays module/provider-oriented, Spring prefers package-by-feature, and so on.

The resolved policy is materialized to:

```text
.vibe/runtime/architecture-policy.json
```

It contains:

- requested/effective profile,
- selected pattern,
- project-size signals,
- auto-strict decision reason,
- recommended framework-native structure,
- dependency-direction rules,
- Clean Code rules.

Core Clean Code defaults include intent-revealing naming, focused functions/modules, shallow control flow where practical, thin transport handlers, explicit errors/dependencies, no hidden mutable global state, no speculative abstraction, behavior-focused tests, and simple code over clever code.

## Persistent context architecture

The kit does not treat chat history or old task folders as the source of truth.

It separates four things:

```text
durable project truth
persistent local state
current-task runtime
cold task history
```

### Durable project truth

Committed project information remains authoritative:

```text
AGENTS.md
.vibe/config.json
source code
tests
package manifests
architecture docs
```

### Persistent state across sessions

Reusable local state lives in:

```text
.vibe/state/
├── index-state.json
├── file-index.json
├── last-context.json
├── last-dependency.json
├── last-framework.json
├── last-adapter.json
└── last-architecture.json
```

`.vibe/state/` is ignored by `.vibe/.gitignore`.

It is a performance cache, not project truth and not verification evidence.

`index-state.json` records cache schema/scanner versions and the Git repository state associated with cached artifacts.

For a clean repository, Git HEAD is sufficient. For dirty or untracked application files, the runtime hashes only those changed files instead of hashing the whole repository.

### Cache modes

Each context/dependency refresh resolves to one of three states:

```text
CACHE_HIT
    repository state unchanged
    -> reuse last context/dependency

INCREMENTAL_REFRESH
    Git delta detected
    -> update changed files / affected language slice only

FULL_REBUILD
    first run, missing/invalid cache, unavailable Git delta,
    incompatible cache schema/scanner, or forced rebuild
```

A cache hit saves work. It does **not** mean the code passed tests.

### Incremental refresh by language

The zero-dependency baseline currently behaves as follows:

- Python — refresh changed source files only while using the current/cached Python path universe for local import resolution.
- JavaScript/TypeScript — refresh changed files for relative import/export/require edges.
- Vue/Svelte single-file components — tracked as source/context nodes even though embedded-script dependency parsing remains best-effort; framework context identifies components/routes and native tooling remains authoritative.
- PHP — refresh the PHP slice when PHP files or Composer manifests change.
- Java/Kotlin — refresh the JVM slice when JVM files or Maven/Gradle manifests change.
- Go — refresh the Go slice when Go files or `go.mod` changes.
- Rust — refresh the Rust slice when Rust files or `Cargo.toml` changes.

This is intentionally simpler than introducing a database/index service for a personal-project kit.

### Bounded relevant context

Current-task facts are materialized under:

```text
.vibe/runtime/
├── current-task.json
├── project-map.json
├── framework-map.json
├── active-adapter.json
├── architecture-policy.json
├── dependency-map.json
├── relevant-context.json
├── impact.json
├── dependency-diff.json
└── verification.json
```

`relevant-context.json` is deliberately small.

Default first-pass limits:

- 20 source files,
- 10 test files,
- 8 related modules,
- dependency depth 2.

The agent reads this bounded neighborhood first, then expands only when a concrete dependency, consumer, contract, configuration path, or failing test requires more context.

The full dependency graph can exist on disk without being pasted into the model context.

### Task history is cold storage

Per-task audit records live under:

```text
.vibe/tasks/<task-id>/
├── request.md
├── task.json
├── context.json
├── framework.json
├── active-adapter.json
├── architecture-policy.json
├── relevant-context.json
├── impact.json
├── plan.md
├── dependency-before.json
├── dependency-after.json
├── dependency-diff.json
└── verification.json
```

Default policy:

```json
{
  "tasks": {
    "keep_history": true,
    "auto_load_history": false
  }
}
```

A new session must not enumerate and load every old task.

Historical tasks are loaded only when:

- the user explicitly refers to a prior task, or
- current evidence identifies a specific old task as materially relevant.

Current source/tests/config outrank historical task artifacts.

### Why this saves tokens

Repository scanning and graph maintenance happen in deterministic Python code.

The model sees only the relevant bounded neighborhood:

```text
large repository
      ↓
persistent local cache
      ↓
Git delta
      ↓
relevant subgraph
      ↓
bounded source/tests
      ↓
LLM
```

A 5,000-file repository therefore does not imply a 5,000-file model context.

## Default personal-project configuration

The default v0.4-style configuration is intentionally simple:

```json
{
  "version": 3,
  "architecture": {
    "profile": "auto",
    "default_profile": "standard",
    "module_style": "feature-first",
    "default_pattern": "modular-layered",
    "strict_pattern": "hexagonal",
    "framework_conventions": "prefer",
    "allow_auto_strict": true,
    "strict_thresholds": {
      "source_files": 300,
      "feature_roots": 20
    }
  },
  "context": {
    "strategy": "persistent-incremental",
    "max_dependency_depth": 2,
    "max_files": 20000,
    "max_source_files": 20,
    "max_test_files": 10,
    "max_related_modules": 8
  },
  "index": {
    "backend": "json",
    "use_git_delta": true,
    "full_rebuild_on_schema_change": true
  },
  "dependency": {
    "fail_on_new_cycles": true
  },
  "verification": {
    "require_commands": true,
    "commands": []
  },
  "tasks": {
    "keep_history": true,
    "auto_load_history": false
  }
}
```

No SQLite or mandatory symbol database is used by default.

### Frontend architecture defaults

Frontend code follows the same feature-first philosophy but does **not** inherit backend controller/service/repository ceremony by default.

Typical shape:

```text
route/page shell
      ↓
feature UI
      ↓
hooks / composables / stores
      ↓
API / data adapters
```

Useful rules include:

- keep page/route shells thin,
- keep non-trivial business workflows out of presentational components,
- avoid cross-feature imports through another feature's internals,
- keep shared modules independent from feature internals,
- respect server/client boundaries in Next.js, Nuxt and SvelteKit,
- use component tests/integration tests for UI behavior and E2E only for critical flows.

### WordPress architecture defaults

WordPress is treated as a CMS/framework adapter, not just generic PHP.

The standard profile prefers:

```text
WordPress hooks / REST / templates
            ↓
feature-oriented plugin/theme modules
            ↓
services / business behavior
            ↓
WordPress APIs / data adapters
```

The adapter treats hooks, filters, shortcodes, REST routes, block contracts, options/meta, and theme/plugin boundaries as integration contracts. It explicitly prefers WordPress APIs and custom plugin/theme code over modifying WordPress core.

## Core workflow

### Full workflow

```text
PLAN -> BUILD -> VERIFY
```

Example:

```text
Use vibe to add percentage-based trailing stops while preserving old fixed-point configs.
```

### Plan

The plan skill:

1. Reads `AGENTS.md` and `.vibe/config.json`.
2. Starts the current task record.
3. Runs `context` to reuse or incrementally refresh persistent repository context.
4. Runs `deps` to reuse or incrementally refresh the dependency graph.
5. Runs `relevant` to build bounded source/test/module context.
6. Reads only that bounded context first.
7. Expands context only when evidence requires it.
8. Runs impact analysis for identified targets.
9. Produces implementation and verification plans.

### Build

Build:

- reads the current task only,
- starts with `relevant-context.json`,
- follows the architecture policy,
- makes the smallest correct change,
- adds focused tests,
- expands context only when justified by evidence.

### Verify

Verify:

- refreshes context/dependencies through the same cache/delta engine,
- captures dependency state after changes,
- compares dependency snapshots,
- detects new cycles,
- runs configured lint/type/test/build commands,
- reviews the final diff,
- records `verification.json`.

A `CACHE_HIT` does not skip verification commands.

## Change modes

### Feature

Focus:

- desired behavior,
- architecture placement,
- dependency impact,
- acceptance criteria,
- focused tests.

### Change

Focus:

- current behavior,
- desired behavior,
- compatibility,
- affected consumers,
- schema/config/API migration impact.

### Bug fix

Mandatory sequence:

```text
REPRODUCE
-> ROOT CAUSE
-> FAILING REGRESSION TEST
-> MINIMAL FIX
-> PASSING REGRESSION TEST
-> AFFECTED TESTS
-> VERIFY
```

Do not call a bug fixed just because the symptom disappeared manually.

### Refactor

Focus:

- capture baseline behavior,
- dependency snapshot before,
- preserve public behavior/contracts,
- dependency snapshot after,
- prove behavior did not change.

### Hotfix

Rules:

- minimal scope,
- no opportunistic cleanup,
- no dependency upgrades unless required,
- reproduce when practical,
- regression test,
- critical affected verification.

## Testing policy

The kit does not require one direct unit test for every function.

The preferred rule is:

```text
100% of non-trivial business behavior
should have meaningful test coverage
```

Must test when practical:

- public business behavior,
- calculations,
- validation rules,
- important branches,
- failure/error behavior,
- bug regressions.

May be covered indirectly:

- private helpers,
- simple mappings,
- framework glue,
- trivial getters/setters,
- generated code.

Typical strategy:

```text
business logic
-> focused unit tests

repository/database boundary
-> integration tests when useful

API endpoints
-> request/response integration tests

critical user flows
-> E2E when justified

bug
-> mandatory regression test when practical
```

Tests should assert observable behavior rather than internal call counts or implementation details unless the implementation contract itself matters.

## Runtime CLI

```bash
python .vibe/tools/vibe.py detect
python .vibe/tools/vibe.py task start --mode bug_fix --request "stop-loss gap fill is wrong"
python .vibe/tools/vibe.py context
python .vibe/tools/vibe.py adapter
python .vibe/tools/vibe.py framework
python .vibe/tools/vibe.py architecture
python .vibe/tools/vibe.py state
python .vibe/tools/vibe.py deps
python .vibe/tools/vibe.py relevant
python .vibe/tools/vibe.py relevant src/orders/service.py
python .vibe/tools/vibe.py relevant --query "fix order cancellation"
python .vibe/tools/vibe.py impact
python .vibe/tools/vibe.py snapshot before
python .vibe/tools/vibe.py snapshot after
python .vibe/tools/vibe.py verify
python .vibe/tools/vibe.py status
python .vibe/tools/vibe.py rebuild
```

Important commands:

- `state` — shows whether persistent context/dependencies will be reused or refreshed.
- `relevant` — builds bounded task context.
- `rebuild` — forces full context/dependency reconstruction for troubleshooting or large structural changes.

## Dependency analysis

Built-in zero-dependency baseline:

- Python — AST local import graph.
- JavaScript/TypeScript — relative import/export/require graph.
- PHP — namespace/use plus literal require/include relationships.
- Java/Kotlin — package/import relationships.
- Go — local module import relationships.
- Rust — module declarations and `crate::` use relationships.
- Other — project/file map.

Framework context is materialized into `.vibe/runtime/framework-map.json`.

The merged language/framework adapter is materialized into `.vibe/runtime/active-adapter.json`.

Reusable copies live under `.vibe/state/`.

### Recommended native tools

Python:

- Grimp
- Import Linter
- Ruff
- Pyright or mypy
- pytest

TypeScript/JavaScript:

- dependency-cruiser
- Nx for monorepos
- TypeScript compiler
- ESLint
- Vitest/Jest/Playwright

PHP/Laravel:

- Deptrac
- PHPStan/Larastan
- Pest/PHPUnit
- Laravel Pint/PHP-CS-Fixer

Java/Spring:

- Maven/Gradle dependency tooling
- ArchUnit
- jdeps
- Checkstyle/SpotBugs

Go:

- `go list -deps`
- `go mod graph`
- `go vet`
- staticcheck/golangci-lint
- `go test ./...`

Rust:

- `cargo metadata`
- `cargo tree`
- `cargo clippy`
- `cargo test`

The built-in graph is a zero-setup baseline. Native analyzers remain authoritative when configured.

For frontend projects, useful native tooling includes ESLint, TypeScript/Vue/Svelte type-checkers, Vitest/Jest, Testing Library, Playwright/Cypress, and framework build commands. For WordPress, use Composer scripts, PHPUnit/Pest, PHPStan, PHPCS/WordPress Coding Standards, WP-CLI checks, and frontend build/test commands when the project already configures them.

## Dependency snapshots

Before implementation:

```bash
python .vibe/tools/vibe.py deps
python .vibe/tools/vibe.py snapshot before
```

After implementation:

```bash
python .vibe/tools/vibe.py deps
python .vibe/tools/vibe.py snapshot after
```

The diff includes:

- added edges,
- removed edges,
- new cycles,
- removed cycles,
- before/after node counts.

## Verification semantics

Possible statuses:

- `PASS_VERIFIED`
- `FAIL_VERIFICATION`
- `NEEDS_VERIFICATION_CONFIG`

`PASS_VERIFIED` is allowed only when:

1. deterministic context/dependency work completes,
2. forbidden new cycles are absent,
3. required verification commands are configured,
4. those commands actually run,
5. every required command succeeds.

A cache hit is never sufficient evidence for `PASS_VERIFIED`.

## Repository layout

Source repository:

```text
my-vibe-kit/
├── AGENTS.md
├── CLAUDE.md
├── README.md
├── README_vi.md
├── install.py
├── vibe.config.example.json
├── skills/
│   ├── vibe/SKILL.md
│   ├── plan/SKILL.md
│   ├── build/SKILL.md
│   └── verify/SKILL.md
├── runtime/
│   ├── vibe.py
│   ├── vibe_core.py
│   ├── vibe_stacks.py
│   ├── vibe_architecture.py
│   └── vibe_state.py
├── adapters/
│   ├── languages/
│   └── frameworks/
├── integrations/
├── templates/
└── tests/
```

Installed project:

```text
your-project/
├── AGENTS.md
├── CLAUDE.md
├── .agents/
│   ├── skills/
│   ├── rules/
│   └── workflows/
├── .claude/
│   └── skills/
└── .vibe/
    ├── config.json
    ├── adapters/
    ├── tools/
    ├── state/       # persistent local cache; ignored
    ├── runtime/     # current-task materialization; ignored
    └── tasks/       # cold task history; not auto-loaded
```

## Requirements

- Python 3.9+
- Git
- At least one supported coding agent

The kit runtime itself uses only the Python standard library.

The target project may use any supported language/toolchain.

## Agent compatibility

| Surface | Project skills | Personal/global skills | Notes |
| --- | --- | --- | --- |
| Codex desktop / CLI / IDE | `.agents/skills/` | `~/.agents/skills/` | Project install recommended for deterministic runtime |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` | Native filesystem skill discovery |
| Claude app / claude.ai | upload ZIP | upload ZIP | Use `python install.py --bundle-claude` |
| Antigravity IDE | `.agents/skills/` | `~/.gemini/config/skills/` | Project install also adds rules/workflows |
| Antigravity CLI | `.agents/skills/` | `~/.gemini/antigravity-cli/skills/` | Project scope recommended |

For full deterministic context/dependency/verification, install the kit into each target repository.

## Agent-specific installation

### Codex

Project:

```bash
python install.py --target /path/to/project --agents codex
```

Global:

```bash
python install.py --scope global --agents codex
```

### Claude Code

Project:

```bash
python install.py --target /path/to/project --agents claude
```

Global:

```bash
python install.py --scope global --agents claude
```

Create uploadable ZIP bundles for Claude product surfaces:

```bash
python install.py --bundle-claude
```

### Google Antigravity

Project:

```bash
python install.py --target /path/to/project --agents antigravity
```

Global:

```bash
python install.py --scope global --agents antigravity
```

Project install also adds Antigravity rules and slash workflows.

## First-time setup

After installation, inspect:

```text
.vibe/config.json
```

The installer detects the stack, seeds architecture/context defaults, and discovers verification commands when it can do so safely.

Examples:

- Node/TypeScript — `lint`, `typecheck`, `test`, `build` package scripts.
- Python — Ruff, Pyright/mypy, pytest when declared.
- Django — `python manage.py check` plus Django tests where appropriate.
- Laravel/PHP — Composer scripts, PHPStan/Larastan, Pest/PHPUnit, `php artisan test`.
- Java/Spring — Maven/Gradle tests.
- Go — `go test ./...`.
- Rust — `cargo check`, `cargo test`.

If no reliable verification command is discovered, configure it manually.

Example:

```json
{
  "verification": {
    "require_commands": true,
    "commands": [
      ["python", "-m", "ruff", "check", "."],
      ["python", "-m", "pytest", "-q"]
    ]
  }
}
```

## Updating an existing installation

Update the source kit:

```bash
cd /path/to/my-vibe-kit
git pull
```

Preview:

```bash
python install.py --target /path/to/project --agents all --dry-run
```

Apply managed updates:

```bash
python install.py --target /path/to/project --agents all --force
```

`--force` refreshes managed runtime/skills/integration files but intentionally preserves project-owned:

- `AGENTS.md`
- `CLAUDE.md`
- `.vibe/config.json`

When upgrading an older installation, compare the project config with `vibe.config.example.json`. The runtime supplies safe defaults for missing v3 keys, but explicitly merging the new context/index/task settings is recommended.

## Safe installation behavior

The installer:

- creates missing managed files,
- leaves unrelated project files untouched,
- preserves existing project-owned instructions/config,
- reports managed-file conflicts,
- supports `--dry-run`,
- only refreshes kit-managed files with `--force`.

Review the target repository diff before committing.

## Suggested daily use

Most tasks:

```text
Use vibe to implement <request>.
```

Risky task:

```text
Use plan to analyze replacing SQLite with PostgreSQL. Do not edit anything.
```

Then:

```text
Use build for the current task, then verify it.
```

Useful manual inspection:

```bash
python .vibe/tools/vibe.py state
python .vibe/tools/vibe.py relevant
python .vibe/tools/vibe.py status
```

## Troubleshooting

### Agent does not discover a skill

Codex / Antigravity:

```text
.agents/skills/<skill-name>/SKILL.md
```

Claude Code:

```text
.claude/skills/<skill-name>/SKILL.md
```

Restart/reopen the agent if skills were added while it was already running.

### Verification requires configuration

Edit:

```text
.vibe/config.json
```

Add commands representing the project's real quality gates.

### Dependency map misses framework magic

Static graphs cannot see every dynamic import, plugin registry, reflection path, runtime DI binding, generated source, macro, or external service.

Document critical runtime relationships in project instructions/architecture docs and configure native analyzers/tests where appropriate.

### Large repository creates too much context

Inspect:

```bash
python .vibe/tools/vibe.py state
python .vibe/tools/vibe.py relevant
```

Default first-pass limits are 20 source files, 10 tests, 8 related modules, dependency depth 2.

Increase limits only when real tasks require a wider neighborhood.

Do not paste `last-dependency.json` or the entire dependency graph into model context.

### Cache looks stale or the repository was heavily restructured

Inspect:

```bash
python .vibe/tools/vibe.py state
```

Then rebuild:

```bash
python .vibe/tools/vibe.py rebuild
```

### Why JSON instead of SQLite?

The kit is intended primarily for personal projects.

JSON + Git delta is:

- easy to inspect,
- easy to delete/rebuild,
- standard-library-only,
- easy to debug,
- sufficient for typical personal repositories.

SQLite or symbol-level indexing should be introduced only when real repositories demonstrate that JSON loading or file-level retrieval is a bottleneck.

## Philosophy

```text
LLM       -> reasoning and implementation
Scripts   -> deterministic repository facts
State     -> reusable local cache, never truth by itself
Tests     -> behavioral truth
Git       -> history, delta detection, rollback
Skills    -> reusable workflow
AGENTS.md -> durable project rules
```

The goal is not autonomy at any cost.

The goal is personal vibe coding that is **simple, inspectable, repeatable, token-efficient, and difficult to fake**.

## License

MIT
