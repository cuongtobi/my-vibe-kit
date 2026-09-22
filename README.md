# my-vibe-kit

A small, personal **vibe-coding skills template** for working on real repositories with Codex, Claude, and Google Antigravity.

The kit intentionally keeps the agent surface small:

- `vibe` — orchestrates the full change.
- `plan` — builds context, dependency/impact analysis, and a change plan.
- `build` — implements only the approved scope.
- `verify` — proves the change with runtime evidence.

The same skills are materialized into each agent's native project layout by `install.py`, so you maintain **one source of truth** instead of three copies.

## Cài nhanh (Tiếng Việt)

Cài vào một repo đang làm việc:

```bash
git clone https://github.com/cuongtobi/my-vibe-kit.git
cd my-vibe-kit
python install.py --target /duong-dan/toi/project --agents codex claude antigravity
```

Sau đó mở project bằng Codex, Claude Code hoặc Antigravity và dùng bình thường:

```text
Use vibe to add tính năng export CSV cho báo cáo.
```

```text
Use vibe to fix lỗi backtest crash khi history rỗng.
```

```text
Use plan to phân tích việc đổi SQLite sang PostgreSQL. Chưa sửa code.
```

Workflow chính:

```text
vibe
  -> plan: context + dependency + impact + plan
  -> build: code + test
  -> verify: dependency diff + lint/type/test/build + diff review
```

Các file context/dependency được lưu dưới `.vibe/`, không phụ thuộc vào việc chat đã dài bao nhiêu. Với bug, workflow bắt buộc ưu tiên:

```text
reproduce -> root cause -> regression test fail -> minimal fix -> regression test pass -> verify
```

Nếu project chưa có test/lint/typecheck command phù hợp, hãy sửa `.vibe/config.json`. Toolkit sẽ trả `NEEDS_VERIFICATION_CONFIG`, không tự nhận `PASS_VERIFIED`.

## Design goals

- One personal workflow across Codex, Claude Code, and Antigravity.
- Works from native/desktop agent surfaces where filesystem skills are supported and from CLI/IDE agents.
- File-based context instead of relying on chat history.
- Deterministic dependency/context scans before agent reasoning.
- Explicit change modes: `feature`, `change`, `bug_fix`, `refactor`, `hotfix`.
- Minimal-change implementation by default.
- Runtime verification evidence before completion.
- No mandatory Python packages beyond the standard library for the kit itself.
- Optional integration with stronger ecosystem tools such as Grimp, Import Linter, dependency-cruiser, Nx, Deptrac, PHPStan/Larastan, ArchUnit, Cargo tooling, Go tooling, Ruff, Pyright, pytest, TypeScript, ESLint, and Vitest.

## Supported languages and frameworks

The workflow is language-agnostic, while the runtime now has stack-aware adapters and baseline dependency scanners.

| Language | Baseline dependency scan | Framework adapters |
| --- | --- | --- |
| Python | AST import graph | Flask, FastAPI, Django |
| JavaScript | relative import/require graph | Express, Next.js |
| TypeScript | relative import graph | Express, NestJS, Next.js |
| PHP | namespace/use + literal require/include graph | Laravel |
| Java/Kotlin | package/import graph | Spring |
| Go | module-local import graph | Gin, Fiber |
| Rust | mod + crate::use graph | Actix Web |
| Other | project/file map | generic fallback |

Framework adapters add framework-aware context such as routes, controllers/routers, models/components, middleware/providers, and framework-specific verification recommendations.

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

This means the four core skills do not need separate Laravel/Flask/Express variants.

## How it works

```text
User request
    |
    v
  vibe
    |
    +--> plan
    |     +--> load project rules
    |     +--> detect stack
    |     +--> build project context
    |     +--> build dependency graph
    |     +--> impact analysis
    |     +--> write task plan
    |
    +--> build
    |     +--> smallest correct change
    |     +--> tests/regression test
    |     +--> affected checks
    |
    +--> verify
          +--> dependency graph after
          +--> dependency diff
          +--> cycles/architecture checks
          +--> configured lint/type/test/build commands
          +--> git diff review
          +--> verification.json
```

The agent skills contain methodology. The scripts under `.vibe/tools/` produce deterministic repository facts.

## Repository layout

```text
my-vibe-kit/
├── AGENTS.md
├── CLAUDE.md
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
│   └── vibe_stacks.py
├── adapters/
│   ├── languages/
│   │   ├── python.json
│   │   ├── javascript.json
│   │   ├── typescript.json
│   │   ├── php.json
│   │   ├── java.json
│   │   ├── go.json
│   │   ├── rust.json
│   │   └── generic.json
│   └── frameworks/
│       ├── flask.json
│       ├── fastapi.json
│       ├── django.json
│       ├── express.json
│       ├── nestjs.json
│       ├── nextjs.json
│       ├── laravel.json
│       ├── spring.json
│       ├── gin.json
│       ├── fiber.json
│       └── actix-web.json
├── integrations/
│   └── antigravity/
│       ├── rules/vibe-project.md
│       └── workflows/
│           ├── vibe.md
│           ├── plan.md
│           ├── build.md
│           └── verify.md
├── templates/
│   ├── AGENTS.md
│   └── CLAUDE.md
└── tests/
```

After project installation, a target repository receives a layout similar to:

```text
your-project/
├── AGENTS.md
├── CLAUDE.md
├── .agents/
│   ├── skills/
│   │   ├── vibe/
│   │   ├── plan/
│   │   ├── build/
│   │   └── verify/
│   ├── rules/              # Antigravity
│   └── workflows/          # Antigravity slash workflows
├── .claude/
│   └── skills/             # Claude Code project skills
└── .vibe/
    ├── config.json
    ├── adapters/
    ├── tools/
    │   ├── vibe.py
    │   ├── vibe_core.py
    │   └── vibe_stacks.py
    ├── runtime/            # regenerated; ignored by .vibe/.gitignore
    └── tasks/              # task records; keep or archive as you prefer
```

## Requirements

For installing the kit:

- Python 3.9+
- Git
- At least one supported coding agent

The kit runtime itself is standard-library-only. Your target repository can still use any language/toolchain.

## Agent compatibility

| Surface | Project skills | Personal/global skills | Notes |
| --- | --- | --- | --- |
| Codex desktop app / CLI / IDE | `.agents/skills/` | `~/.agents/skills/` | Codex desktop shares the Codex skills/config ecosystem with CLI/IDE. |
| Claude Code | `.claude/skills/` | `~/.claude/skills/` | Filesystem discovery is native to Claude Code. |
| Claude app / claude.ai | upload ZIP | upload ZIP | Run `python install.py --bundle-claude`, then upload the desired skill in the product UI. |
| Antigravity IDE | `.agents/skills/` | `~/.gemini/config/skills/` | Project install also adds rules and slash workflows. |
| Antigravity CLI | `.agents/skills/` | `~/.gemini/antigravity-cli/skills/` compatibility copy | Project scope is recommended because it travels with the repo. |

For **full deterministic context/dependency/verification**, install the kit into each repository. A global skill install gives the agent the workflow everywhere, but a project install is what adds `.vibe/tools/`, `.vibe/config.json`, task storage, and repository-local verification configuration.

Current format/location references:

- OpenAI Skills: https://developers.openai.com/docs/build-skills
- Anthropic Agent Skills: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- Google Antigravity Skills: https://codelabs.developers.google.com/getting-started-with-antigravity-skills

## Quick start

Clone the kit once:

```bash
git clone https://github.com/cuongtobi/my-vibe-kit.git
cd my-vibe-kit
```

Install it into a project:

```bash
python install.py --target /path/to/your-project --agents codex claude antigravity
```

On Windows PowerShell:

```powershell
python .\install.py --target C:\code\your-project --agents codex claude antigravity
```

Preview without writing:

```bash
python install.py --target /path/to/your-project --agents all --dry-run
```

The installer does not overwrite conflicting project files unless you explicitly pass `--force`.

## Agent-specific installation

### Codex

Repository skills are installed to:

```text
<project>/.agents/skills/
```

That layout is shared with Antigravity project skills, so installing both does not create duplicate skill sources in the target repository.

Recommended project install:

```bash
python install.py --target /path/to/project --agents codex
```

For personal/global Codex skills:

```bash
python install.py --scope global --agents codex
```

This installs skills under:

```text
~/.agents/skills/
```

### Codex desktop app

Codex desktop uses the same Codex skills/config ecosystem as CLI/IDE. Install the skills globally or into the repository, restart/reopen the project if the skills were added while Codex was already running, and open the local repository in the Codex view. The repository-local install is recommended because the deterministic runtime and task context travel with the project.

Use from Codex desktop/CLI/IDE by describing the task normally, or explicitly ask it to use the `vibe`, `plan`, `build`, or `verify` skill.

Example:

```text
Use the vibe skill to fix the backtest stop-loss fill bug when the market gaps below the stop.
```

### Claude Code

Claude Code project skills live under:

```text
<project>/.claude/skills/
```

Install:

```bash
python install.py --target /path/to/project --agents claude
```

The installer also creates `CLAUDE.md` when it does not already exist. The generated file imports the shared `AGENTS.md`, so project rules stay in one place.

Personal Claude Code skills:

```bash
python install.py --scope global --agents claude
```

They are installed to:

```text
~/.claude/skills/
```

For Claude app / claude.ai surfaces that accept uploaded custom Skills, create uploadable Skill archives locally:

```bash
python install.py --bundle-claude
```

The command writes ZIP files to `dist/claude-skills/`. Upload the desired skill from the Claude product's Skills/Features UI. The ZIP creation happens on your machine; no repository access is required.

### Google Antigravity IDE / native app

Antigravity workspace skills use:

```text
<project>/.agents/skills/
```

The kit additionally installs:

```text
<project>/.agents/rules/vibe-project.md
<project>/.agents/workflows/vibe.md
<project>/.agents/workflows/plan.md
<project>/.agents/workflows/build.md
<project>/.agents/workflows/verify.md
```

Install:

```bash
python install.py --target /path/to/project --agents antigravity
```

You can then use saved workflows such as:

```text
/vibe Fix the duplicate order bug in paper trading
/plan Add CSV export to the report screen
/build
/verify
```

### Antigravity CLI

Project scope uses the same `.agents/skills/` directory, so the normal project install is the recommended approach.

For global installation:

```bash
python install.py --scope global --agents antigravity
```

The installer writes to the Antigravity global skills location and also creates the Antigravity CLI compatibility copy when applicable.

## First-time setup in a target project

After installing, open:

```text
.vibe/config.json
```

The installer detects the repository language/framework stack and seeds verification commands when it can do so safely. It also copies the language/framework adapter catalog into `.vibe/adapters/`.

Examples of automatically discovered gates include:

- Node/TypeScript: package scripts such as `lint`, `typecheck`, `test`, `build`.
- Python: Ruff, Pyright/mypy, pytest when declared.
- Django: `python manage.py check`, plus Django tests when pytest is not configured.
- Laravel/PHP: Composer test scripts, PHPStan/Larastan, Pest/PHPUnit, or `php artisan test`.
- Java/Spring: Maven or Gradle tests.
- Go: `go test ./...`.
- Rust: `cargo check` and `cargo test`.

For a Node/TypeScript project, package scripts are preferred. If `package.json` contains:

```json
{
  "scripts": {
    "lint": "eslint .",
    "typecheck": "tsc --noEmit",
    "test": "vitest run",
    "build": "vite build"
  }
}
```

the generated configuration can invoke those scripts.

For Python, the installer looks for common local tooling and project configuration. You can edit the commands explicitly:

```json
{
  "verification": {
    "commands": [
      ["python", "-m", "ruff", "check", "."],
      ["python", "-m", "pytest", "-q"]
    ],
    "require_commands": true
  }
}
```

If no reliable verification command can be determined, the kit does **not** pretend the project is verified. `verify` reports that configuration is required instead of emitting `PASS_VERIFIED`.

## Core workflow

### 1. Full vibe workflow

Typical request:

```text
Use vibe to add percentage-based trailing stops while preserving old fixed-point configs.
```

The orchestrator selects a mode and follows:

```text
PLAN -> BUILD -> VERIFY
```

### 2. Plan only

Use this when you want to inspect scope before editing:

```text
Use plan to analyze adding OAuth login. Do not modify code.
```

The plan skill:

1. Reads `AGENTS.md` and relevant repository instructions.
2. Starts/updates a task record.
3. Runs stack/context scan.
4. Runs dependency scan.
5. Finds reverse dependencies and likely tests.
6. Writes impact analysis.
7. Produces an implementation plan.

### 3. Build from an existing plan

```text
Use build to implement the current vibe task.
```

Build follows the current task artifacts and does not expand scope silently.

### 4. Verify

```text
Use verify on the current change.
```

Verify rebuilds dependency facts, compares snapshots, runs configured commands, and records evidence.

## Change modes

The same four skills cover different kinds of work.

### Feature

```text
Add CSV export to the trades report.
```

Plan focus:

- desired behavior
- architecture placement
- dependency impact
- acceptance criteria
- new tests

### Change

```text
Change trailing stops from fixed points to percentages while keeping old configs working.
```

Plan focus:

- current behavior
- desired behavior
- compatibility
- affected consumers
- migration/config impact

### Bug fix

```text
Backtest fills a stop order at the stop price when the market gaps through it.
```

Mandatory bug workflow:

```text
REPRODUCE
   -> ROOT CAUSE
   -> FAILING REGRESSION TEST
   -> MINIMAL FIX
   -> PASSING REGRESSION TEST
   -> AFFECTED TESTS
   -> VERIFY
```

The agent should not call a bug fixed merely because the symptom disappeared manually.

### Refactor

```text
Split the backtest engine into smaller modules without changing behavior.
```

Refactor focus:

- capture baseline behavior
- dependency snapshot before
- preserve public API unless explicitly allowed
- dependency snapshot after
- prove behavior remains unchanged

### Hotfix

Hotfixes deliberately minimize scope:

- no opportunistic cleanup
- no dependency upgrades unless required for the fix
- reproduce when possible
- smallest patch
- regression test
- critical affected verification

## Runtime context

The kit does not treat a long chat as the source of truth.

It uses three context layers.

### Persistent project context

Committed files such as:

```text
AGENTS.md
architecture docs
source code
tests
package manifests
.vibe/config.json
```

### Derived context

Regenerated under:

```text
.vibe/runtime/
├── project-map.json
├── framework-map.json
├── active-adapter.json
├── dependency-map.json
├── impact.json
├── dependency-diff.json
└── verification.json
```

This directory is ignored by `.vibe/.gitignore`.

### Task context

Each task gets a record:

```text
.vibe/tasks/<task-id>/
├── request.md
├── task.json
├── context.json
├── impact.json
├── plan.md
├── dependency-before.json
├── dependency-after.json
├── dependency-diff.json
└── verification.json
```

Not every file must exist for every tiny task. The skills create only what is useful.

Task history is intentionally not ignored by default. You can commit it for architectural traceability or archive/delete it after merge.

## Runtime CLI

The installed toolkit exposes:

```bash
python .vibe/tools/vibe.py detect
python .vibe/tools/vibe.py task start --mode bug_fix --request "stop-loss gap fill is wrong"
python .vibe/tools/vibe.py context
python .vibe/tools/vibe.py adapter
python .vibe/tools/vibe.py framework
python .vibe/tools/vibe.py deps
python .vibe/tools/vibe.py impact
python .vibe/tools/vibe.py snapshot before
python .vibe/tools/vibe.py snapshot after
python .vibe/tools/vibe.py verify
python .vibe/tools/vibe.py status
```

The skills call these commands when appropriate. You can also run them manually when debugging the workflow.

## Dependency analysis

The built-in scanner is intentionally dependency-free and acts as a baseline:

- Python: AST-based local import graph.
- JavaScript/TypeScript: local relative import/export/require graph.
- PHP: namespace/use relationships plus literal require/include paths.
- Java/Kotlin: package/import relationships.
- Go: local module import relationships.
- Rust: module declarations and `crate::` use relationships.
- Generic projects: file/project map when a language-specific graph is unavailable.

Framework context is also generated into `.vibe/runtime/framework-map.json`, while the merged stack adapter is stored in `.vibe/runtime/active-adapter.json`.

For larger projects, use stronger native tooling too.

### Python recommendation

Add to your project as appropriate:

- Grimp — dependency graph queries.
- Import Linter — architecture contracts.
- Ruff — lint/static checks.
- Pyright or mypy — type checks.
- pytest — behavior/regression tests.

Then configure those verification commands in `.vibe/config.json`.

### TypeScript recommendation

Useful additions:

- dependency-cruiser — module graph, cycle/rule checks.
- Nx — project graph and affected analysis for monorepos.
- TypeScript compiler — semantic/type checking.
- ESLint — static rules.
- Vitest/Jest/Playwright — behavioral verification.

### PHP / Laravel recommendation

Useful additions:

- Deptrac — enforce architectural layer rules.
- PHPStan / Larastan — semantic/static analysis.
- Pest or PHPUnit — behavior/regression tests.
- Laravel Pint or PHP-CS-Fixer — style/static hygiene.

### Java / Spring recommendation

Useful additions:

- Maven/Gradle dependency tooling.
- ArchUnit — enforce package/module architecture.
- jdeps — JVM dependency inspection.
- Checkstyle / SpotBugs — static quality checks.

### Go recommendation

Useful additions:

- `go list -deps` and `go mod graph`.
- `go vet`.
- staticcheck or golangci-lint.
- `go test ./...`.

### Rust recommendation

Useful additions:

- `cargo metadata`.
- `cargo tree`.
- `cargo clippy`.
- `cargo test`.

The kit's graph remains useful as a zero-setup baseline; native analyzers remain the authority when configured.

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

Then verification produces a dependency diff including:

- added edges
- removed edges
- newly introduced cycles
- changed module counts

This makes accidental architectural coupling visible to the agent.

## Verification semantics

`PASS_VERIFIED` is intentionally strict.

It can only be emitted when:

1. dependency/context commands actually completed,
2. no newly introduced dependency cycle violates the baseline,
3. at least one configured verification command actually ran when `require_commands` is true,
4. every required command exited successfully.

Possible states include:

- `PASS_VERIFIED`
- `FAIL_VERIFICATION`
- `NEEDS_VERIFICATION_CONFIG`

This prevents an agent from declaring success based only on its own reading of the code.

## AGENTS.md

Keep `AGENTS.md` short. It is always-on project context.

Recommended content:

- architecture invariants
- coding conventions that really matter
- commands/source of truth
- forbidden changes
- definition of done

Do not put long task procedures there. Those belong in on-demand skills.

## Updating the kit in an existing project

Pull the latest kit:

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

Review the target repository diff before committing.

## Safe installation behavior

By default the installer:

- creates missing managed files,
- leaves unrelated project files untouched,
- preserves an existing project-owned `AGENTS.md`, `CLAUDE.md`, and `.vibe/config.json`,
- refuses to overwrite a different kit-managed destination,
- reports true managed-file conflicts,
- supports `--dry-run`.

`--force` refreshes kit-managed skills/runtime/integration files. It still does **not** overwrite your project-owned instructions or config. Review the target repository diff before committing.

## Suggested daily use

For most tasks, use just one request:

```text
Use vibe to implement <request>.
```

Examples:

```text
Use vibe to add an export-to-CSV button to the analytics page.
```

```text
Use vibe to fix the crash when backtest history is empty.
```

```text
Use vibe to refactor the order execution module without behavior changes.
```

For risky changes, plan first:

```text
Use plan to analyze replacing SQLite with PostgreSQL. Do not edit anything.
```

Then review the plan and tell the agent:

```text
Use build for the current task, then verify it.
```

## Troubleshooting

### Agent does not discover a skill

Check the project path:

Codex / Antigravity:

```text
.agents/skills/<skill-name>/SKILL.md
```

Claude Code:

```text
.claude/skills/<skill-name>/SKILL.md
```

Restart the agent if it was already running when skills were installed.

### Verification says configuration is required

Edit:

```text
.vibe/config.json
```

and add commands that represent your repository's real gates.

### Dependency map misses framework magic

Static import graphs cannot see every dynamic dependency, plugin registry, reflection path, runtime DI binding, generated source, or external service.

Document critical runtime relationships in `AGENTS.md` or architecture docs and configure native analyzers/tests where available.

### A large repository creates too much context

The runtime stores the full machine-readable map on disk, but the skill should summarize only the relevant neighborhood:

- target files
- direct dependencies
- reverse dependencies
- bounded transitive dependencies
- affected tests

Do not paste the entire dependency graph into the model context.

## Philosophy

```text
LLM       -> reasoning and implementation
Scripts   -> deterministic repository facts
Tests     -> behavioral truth
Git       -> history and rollback
Skills    -> reusable workflow
AGENTS.md -> durable project rules
```

The purpose of my-vibe-kit is not to make the agent autonomous at any cost. It is to make personal vibe coding **simple, inspectable, repeatable, and difficult to fake**.

## License

MIT
