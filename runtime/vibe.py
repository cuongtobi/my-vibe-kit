#!/usr/bin/env python3
"""CLI entry point installed as .vibe/tools/vibe.py in target repositories."""

import argparse
import json
import sys
from pathlib import Path

from vibe_core import (
    dependency_graph,
    detect_stack,
    impact_analysis,
    project_context,
    relevant_context,
    repository_root,
    snapshot_dependencies,
    start_task,
    status,
    verify,
)
from vibe_state import load_cache, state_summary


def emit(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="my-vibe-kit deterministic repository runtime")
    root.add_argument(
        "--root",
        default=".",
        help="Repository root or a path inside the repository. Defaults to current directory.",
    )
    sub = root.add_subparsers(dest="command", required=True)

    sub.add_parser("detect", help="Detect repository stack.")
    sub.add_parser("context", help="Build .vibe/runtime/project-map.json.")
    sub.add_parser("deps", help="Build .vibe/runtime/dependency-map.json.")
    sub.add_parser("framework", help="Build framework-aware route/component context.")
    sub.add_parser("adapter", help="Resolve the active language + framework adapters.")
    sub.add_parser("architecture", help="Read the effective cached architecture profile and clean-code policy.")
    sub.add_parser("state", help="Show persistent cache state and whether context/dependencies can be reused.")
    sub.add_parser("rebuild", help="Force a full rebuild of persistent context and dependency caches.")

    relevant = sub.add_parser("relevant", help="Build bounded task context without loading the whole repository.")
    relevant.add_argument("files", nargs="*", help="Optional explicit target files.")
    relevant.add_argument("--query", help="Optional relevance query; defaults to the current task request.")

    impact = sub.add_parser("impact", help="Compute reverse dependency and test impact.")
    impact.add_argument("files", nargs="*", help="Target files. Defaults to changed git files.")

    task = sub.add_parser("task", help="Manage task records.")
    task_sub = task.add_subparsers(dest="task_command", required=True)
    start = task_sub.add_parser("start", help="Start and persist a new task.")
    start.add_argument(
        "--mode",
        required=True,
        choices=("feature", "change", "bug_fix", "refactor", "hotfix"),
    )
    request_group = start.add_mutually_exclusive_group(required=True)
    request_group.add_argument("--request", help="Short normalized task request.")
    request_group.add_argument("--request-file", help="Read the request from a UTF-8 file.")

    snapshot = sub.add_parser("snapshot", help="Persist dependency snapshot for current task.")
    snapshot.add_argument("when", choices=("before", "after"))

    sub.add_parser("verify", help="Run deterministic verification and configured project checks.")
    sub.add_parser("status", help="Show current task/runtime status.")
    return root


def resolve_request(args: argparse.Namespace) -> str:
    if args.request is not None:
        return args.request
    path = Path(args.request_file)
    return path.read_text(encoding="utf-8").strip()


def main() -> int:
    args = parser().parse_args()
    requested_root = Path(args.root).expanduser()
    repo = repository_root(requested_root)

    if args.command == "detect":
        emit(detect_stack(repo))
        return 0
    if args.command == "context":
        emit(project_context(repo))
        return 0
    if args.command == "deps":
        emit(dependency_graph(repo))
        return 0
    if args.command == "framework":
        project_context(repo)
        emit(load_cache(repo, "framework", {}))
        return 0
    if args.command == "adapter":
        project_context(repo)
        emit(load_cache(repo, "adapter", {}))
        return 0
    if args.command == "architecture":
        project_context(repo)
        emit(load_cache(repo, "architecture", {}))
        return 0
    if args.command == "state":
        emit(state_summary(repo))
        return 0
    if args.command == "rebuild":
        context = project_context(repo, force=True)
        graph = dependency_graph(repo, force=True)
        emit({
            "context_cache": context.get("cache"),
            "dependency_cache": graph.get("cache"),
            "source_files": context.get("source_file_count"),
            "dependency_nodes": len(graph.get("nodes") or []),
            "dependency_edges": len(graph.get("edges") or []),
        })
        return 0
    if args.command == "relevant":
        emit(relevant_context(repo, args.files or None, args.query))
        return 0
    if args.command == "impact":
        emit(impact_analysis(repo, args.files or None))
        return 0
    if args.command == "task" and args.task_command == "start":
        request = resolve_request(args)
        if not request:
            raise SystemExit("Task request cannot be empty.")
        emit(start_task(repo, args.mode, request))
        return 0
    if args.command == "snapshot":
        data = snapshot_dependencies(repo, args.when)
        emit(
            {
                "snapshot": args.when,
                "nodes": len(data.get("nodes") or []),
                "edges": len(data.get("edges") or []),
                "cycles": len(data.get("cycles") or []),
            }
        )
        return 0
    if args.command == "verify":
        report = verify(repo)
        emit(report)
        if report["status"] == "PASS_VERIFIED":
            return 0
        if report["status"] == "NEEDS_VERIFICATION_CONFIG":
            return 3
        return 1
    if args.command == "status":
        emit(status(repo))
        return 0
    raise SystemExit("Unknown command")


if __name__ == "__main__":
    sys.exit(main())
