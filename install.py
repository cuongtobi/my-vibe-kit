#!/usr/bin/env python3
"""Install my-vibe-kit into a project or into supported user skill locations."""

import argparse
import json
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

ROOT = Path(__file__).resolve().parent
VERSION = "0.1.0"
SUPPORTED_AGENTS = ("codex", "claude", "antigravity")


def normalize_agents(values: Sequence[str]) -> List[str]:
    values = list(values or ["all"])
    if "all" in values:
        return list(SUPPORTED_AGENTS)
    unknown = [value for value in values if value not in SUPPORTED_AGENTS]
    if unknown:
        raise SystemExit("Unsupported agent(s): " + ", ".join(unknown))
    seen = []
    for value in values:
        if value not in seen:
            seen.append(value)
    return seen


def same_content(src: Path, dst: Path) -> bool:
    try:
        return src.read_bytes() == dst.read_bytes()
    except OSError:
        return False


def write_text_safe(
    dst: Path,
    content: str,
    *,
    dry_run: bool,
    force: bool,
    protect_existing: bool = False,
) -> str:
    if dst.exists():
        try:
            if dst.read_text(encoding="utf-8") == content:
                return "unchanged"
        except (OSError, UnicodeDecodeError):
            pass
        if protect_existing:
            return "preserved"
        if not force:
            return "conflict"
    if dry_run:
        return "would-write"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(content, encoding="utf-8")
    return "written"


def copy_file_safe(
    src: Path,
    dst: Path,
    *,
    dry_run: bool,
    force: bool,
    protect_existing: bool = False,
) -> str:
    if dst.exists():
        if same_content(src, dst):
            return "unchanged"
        if protect_existing:
            return "preserved"
        if not force:
            return "conflict"
    if dry_run:
        return "would-write"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(str(src), str(dst))
    return "written"


def copy_tree_safe(
    src: Path,
    dst: Path,
    *,
    dry_run: bool,
    force: bool,
    events: List[Dict[str, str]],
) -> None:
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        target = dst / rel
        status = copy_file_safe(path, target, dry_run=dry_run, force=force)
        events.append({"path": str(target), "status": status})


def detect_stack(target: Path) -> Dict[str, object]:
    markers = {
        "python": ["pyproject.toml", "requirements.txt", "setup.py", "setup.cfg"],
        "node": ["package.json"],
        "typescript": ["tsconfig.json"],
        "rust": ["Cargo.toml"],
        "go": ["go.mod"],
        "java": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "dotnet": ["global.json"],
    }
    found = {}
    for name, candidates in markers.items():
        present = [item for item in candidates if (target / item).exists()]
        if present:
            found[name] = present
    if "typescript" in found:
        primary = "typescript"
    elif "node" in found:
        primary = "javascript"
    elif "python" in found:
        primary = "python"
    elif found:
        primary = sorted(found)[0]
    else:
        primary = "generic"
    return {"primary": primary, "markers": found}


def package_runner(target: Path) -> List[str]:
    if (target / "pnpm-lock.yaml").exists():
        return ["pnpm", "run"]
    if (target / "yarn.lock").exists():
        return ["yarn"]
    return ["npm", "run"]


def discover_verification_commands(target: Path) -> List[List[str]]:
    commands = []
    package_json = target / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts") or {}
            runner = package_runner(target)
            for name in ("lint", "typecheck", "test", "build"):
                if name in scripts:
                    commands.append(runner + [name])
        except (OSError, json.JSONDecodeError):
            pass

    python_text = ""
    for filename in ("pyproject.toml", "requirements.txt", "requirements-dev.txt"):
        path = target / filename
        if path.exists():
            try:
                python_text += "\n" + path.read_text(encoding="utf-8").lower()
            except (OSError, UnicodeDecodeError):
                pass

    if python_text:
        if "ruff" in python_text:
            commands.append(["python", "-m", "ruff", "check", "."])
        if "pyright" in python_text:
            commands.append(["pyright"])
        elif "mypy" in python_text:
            commands.append(["python", "-m", "mypy", "."])
        if "pytest" in python_text:
            commands.append(["python", "-m", "pytest", "-q"])

    unique = []
    seen = set()
    for command in commands:
        key = tuple(command)
        if key not in seen:
            unique.append(command)
            seen.add(key)
    return unique


def default_config(target: Path) -> Dict[str, object]:
    return {
        "version": 1,
        "stack": detect_stack(target),
        "context": {
            "max_dependency_depth": 3,
            "max_files": 20000,
        },
        "dependency": {
            "fail_on_new_cycles": True,
        },
        "verification": {
            "require_commands": True,
            "commands": discover_verification_commands(target),
        },
        "tasks": {
            "keep_history": True,
        },
    }


def install_project(
    target: Path,
    agents: Sequence[str],
    *,
    dry_run: bool,
    force: bool,
) -> List[Dict[str, str]]:
    if target.resolve() == ROOT.resolve():
        raise SystemExit("Refusing to install the kit into its own source repository.")
    if not target.exists() and not dry_run:
        target.mkdir(parents=True, exist_ok=True)

    events = []

    # Durable project instructions are user-owned once created.
    events.append(
        {
            "path": str(target / "AGENTS.md"),
            "status": copy_file_safe(
                ROOT / "templates" / "AGENTS.md",
                target / "AGENTS.md",
                dry_run=dry_run,
                force=False,
                protect_existing=True,
            ),
        }
    )
    if "claude" in agents:
        events.append(
            {
                "path": str(target / "CLAUDE.md"),
                "status": copy_file_safe(
                    ROOT / "templates" / "CLAUDE.md",
                    target / "CLAUDE.md",
                    dry_run=dry_run,
                    force=False,
                    protect_existing=True,
                ),
            }
        )

    # Runtime is managed by the kit and can be refreshed with --force.
    copy_tree_safe(
        ROOT / "runtime",
        target / ".vibe" / "tools",
        dry_run=dry_run,
        force=force,
        events=events,
    )
    copy_tree_safe(
        ROOT / "adapters",
        target / ".vibe" / "adapters",
        dry_run=dry_run,
        force=force,
        events=events,
    )

    config_path = target / ".vibe" / "config.json"
    config_text = json.dumps(default_config(target), indent=2, ensure_ascii=False) + "\n"
    events.append(
        {
            "path": str(config_path),
            "status": write_text_safe(
                config_path,
                config_text,
                dry_run=dry_run,
                force=False,
                protect_existing=True,
            ),
        }
    )

    events.append(
        {
            "path": str(target / ".vibe" / ".gitignore"),
            "status": write_text_safe(
                target / ".vibe" / ".gitignore",
                "runtime/\n",
                dry_run=dry_run,
                force=force,
            ),
        }
    )

    if "codex" in agents or "antigravity" in agents:
        copy_tree_safe(
            ROOT / "skills",
            target / ".agents" / "skills",
            dry_run=dry_run,
            force=force,
            events=events,
        )

    if "claude" in agents:
        copy_tree_safe(
            ROOT / "skills",
            target / ".claude" / "skills",
            dry_run=dry_run,
            force=force,
            events=events,
        )

    if "antigravity" in agents:
        copy_tree_safe(
            ROOT / "integrations" / "antigravity" / "rules",
            target / ".agents" / "rules",
            dry_run=dry_run,
            force=force,
            events=events,
        )
        copy_tree_safe(
            ROOT / "integrations" / "antigravity" / "workflows",
            target / ".agents" / "workflows",
            dry_run=dry_run,
            force=force,
            events=events,
        )

    manifest = {
        "kit_version": VERSION,
        "agents": list(agents),
        "managed_roots": [
            ".vibe/tools",
            ".vibe/adapters",
            ".agents/skills",
            ".claude/skills",
            ".agents/rules",
            ".agents/workflows",
        ],
        "note": "AGENTS.md, CLAUDE.md and .vibe/config.json are user-owned after first creation.",
    }
    events.append(
        {
            "path": str(target / ".vibe" / "install-manifest.json"),
            "status": write_text_safe(
                target / ".vibe" / "install-manifest.json",
                json.dumps(manifest, indent=2) + "\n",
                dry_run=dry_run,
                force=True,
            ),
        }
    )
    return events


def global_skill_destinations(agent: str) -> List[Path]:
    home = Path.home()
    if agent == "codex":
        return [home / ".agents" / "skills"]
    if agent == "claude":
        return [home / ".claude" / "skills"]
    if agent == "antigravity":
        return [
            home / ".gemini" / "config" / "skills",
            home / ".gemini" / "antigravity-cli" / "skills",
        ]
    raise ValueError(agent)


def install_global(
    agents: Sequence[str],
    *,
    dry_run: bool,
    force: bool,
) -> List[Dict[str, str]]:
    events = []
    for agent in agents:
        for destination in global_skill_destinations(agent):
            copy_tree_safe(
                ROOT / "skills",
                destination,
                dry_run=dry_run,
                force=force,
                events=events,
            )

    runtime_home = Path.home() / ".my-vibe-kit"
    copy_tree_safe(
        ROOT / "runtime",
        runtime_home / "tools",
        dry_run=dry_run,
        force=force,
        events=events,
    )
    copy_tree_safe(
        ROOT / "adapters",
        runtime_home / "adapters",
        dry_run=dry_run,
        force=force,
        events=events,
    )
    return events


def bundle_claude(force: bool = False) -> List[Path]:
    out_dir = ROOT / "dist" / "claude-skills"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = []
    for skill_dir in sorted((ROOT / "skills").iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            continue
        out = out_dir / (skill_dir.name + ".zip")
        if out.exists() and not force:
            outputs.append(out)
            continue
        with zipfile.ZipFile(str(out), "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(skill_dir.rglob("*")):
                if path.is_file():
                    archive.write(str(path), str(path.relative_to(skill_dir)))
        outputs.append(out)
    return outputs


def print_events(events: Iterable[Dict[str, str]]) -> int:
    conflicts = 0
    for event in events:
        print("{:<12} {}".format(event["status"], event["path"]))
        if event["status"] == "conflict":
            conflicts += 1
    if conflicts:
        print("\n{} conflict(s) were preserved. Re-run with --force only for kit-managed files.".format(conflicts))
    return conflicts


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install my-vibe-kit.")
    parser.add_argument(
        "--agents",
        nargs="+",
        default=["all"],
        help="codex claude antigravity, or all",
    )
    parser.add_argument(
        "--scope",
        choices=("project", "global"),
        default="project",
        help="Install into a repository or user-level skill locations.",
    )
    parser.add_argument(
        "--target",
        default=".",
        help="Target repository for project scope.",
    )
    parser.add_argument("--force", action="store_true", help="Refresh conflicting kit-managed files.")
    parser.add_argument("--dry-run", action="store_true", help="Show actions without writing.")
    parser.add_argument(
        "--bundle-claude",
        action="store_true",
        help="Build ZIP archives for Claude app/claude.ai custom-skill upload.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    agents = normalize_agents(args.agents)

    if args.bundle_claude:
        outputs = bundle_claude(force=args.force)
        for output in outputs:
            print("bundled      {}".format(output))
        if args.scope == "project" and args.target == "." and args.agents == ["all"]:
            return 0

    if args.scope == "global":
        events = install_global(agents, dry_run=args.dry_run, force=args.force)
    else:
        target = Path(args.target).expanduser().resolve()
        events = install_project(target, agents, dry_run=args.dry_run, force=args.force)

    conflicts = print_events(events)
    print("\nInstalled my-vibe-kit {} for: {}".format(VERSION, ", ".join(agents)))
    return 2 if conflicts else 0


if __name__ == "__main__":
    sys.exit(main())
