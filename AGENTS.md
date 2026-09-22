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

## Verification

Run:

```bash
python -m unittest discover -s tests -v
python -m py_compile install.py runtime/vibe.py runtime/vibe_core.py runtime/vibe_stacks.py runtime/vibe_architecture.py runtime/vibe_state.py
```

A change is not complete if these checks fail.
