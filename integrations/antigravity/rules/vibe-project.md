# Vibe project rule

Read and follow the repository's `AGENTS.md` as durable project context.

For non-trivial code changes prefer the installed vibe workflow:

PLAN -> BUILD -> VERIFY -> COMPLETE

Use deterministic facts from `.vibe/tools/vibe.py` when available. Do not claim `PASS_VERIFIED` unless verification commands actually ran and produced that status. Do not report the task finished unless structured acceptance/security evidence has been recorded and `vibe.py complete --summary` reports `COMPLETE`.
