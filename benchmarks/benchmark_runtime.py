#!/usr/bin/env python3
"""Synthetic performance benchmark for my-vibe-kit.

Creates Git repositories with 1k/5k/20k Python source files by default and measures
full indexing, dependency graph construction, cache hits, task retrieval, and a
single-file incremental refresh.
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime"))

import vibe_core  # noqa: E402


def run(command: List[str], cwd: Path) -> None:
    proc = subprocess.run(
        command,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            "{} failed: {}".format(" ".join(command), proc.stdout + proc.stderr)
        )


def timed(fn):
    started = time.perf_counter()
    value = fn()
    return value, round(time.perf_counter() - started, 4)


def create_repo(root: Path, size: int) -> None:
    (root / ".vibe").mkdir(parents=True)
    config = {
        "version": 3,
        "context": {
            "strategy": "persistent-incremental",
            "max_dependency_depth": 2,
            "max_files": size + 200,
            "max_source_files": 20,
            "max_test_files": 10,
            "max_related_modules": 8,
            "retrieval": {
                "min_index_score": 6,
                "fallback_max_scan_files": size + 50,
                "fallback_read_bytes": 131072,
                "query_aliases": {},
            },
        },
        "index": {"backend": "json", "use_git_delta": True},
        "dependency": {"fail_on_new_cycles": True},
        "verification": {"require_commands": True, "commands": []},
        "tasks": {
            "auto_load_history": False,
            "retention": {
                "policy": "bounded",
                "max_tasks": 100,
                "max_age_days": 90,
                "cleanup": "manual",
            },
        },
    }
    (root / ".vibe/config.json").write_text(
        json.dumps(config, indent=2) + "\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        '[project]\nname = "vibe-benchmark"\nversion = "0.0.0"\n',
        encoding="utf-8",
    )

    package = root / "src" / "pkg"
    package.mkdir(parents=True)
    for index in range(size):
        path = package / "mod_{:05d}.py".format(index)
        lines = []
        if index:
            lines.append(
                "from pkg.mod_{:05d} import value as previous_value".format(index - 1)
            )
        if index == size // 2:
            lines.extend(
                [
                    "def refresh_access_token(session):",
                    "    if session.expired:",
                    "        return rotate_token(session)",
                    "",
                    "def rotate_token(session):",
                    "    return session",
                ]
            )
        lines.append("value = {}".format(index))
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    run(["git", "init"], root)
    run(["git", "config", "user.email", "benchmark@example.com"], root)
    run(["git", "config", "user.name", "Vibe Benchmark"], root)
    run(["git", "add", "."], root)
    run(["git", "commit", "-m", "benchmark baseline"], root)


def benchmark_size(size: int) -> Dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="my-vibe-kit-bench-") as tmp:
        root = Path(tmp)
        _, setup_seconds = timed(lambda: create_repo(root, size))

        context, context_rebuild = timed(lambda: vibe_core.project_context(root, force=True))
        graph, dependency_rebuild = timed(lambda: vibe_core.dependency_graph(root))

        cached_context, context_hit = timed(lambda: vibe_core.project_context(root))
        cached_graph, dependency_hit = timed(lambda: vibe_core.dependency_graph(root))

        vibe_core.start_task(
            root,
            "bug_fix",
            "Sửa đăng nhập khi phiên hết hạn và làm mới token",
        )
        relevant, retrieval = timed(lambda: vibe_core.relevant_context(root))

        changed = root / "src" / "pkg" / "mod_{:05d}.py".format(size // 3)
        changed.write_text(
            changed.read_text(encoding="utf-8") + "changed_value = True\n",
            encoding="utf-8",
        )
        inc_context, context_incremental = timed(lambda: vibe_core.project_context(root))
        inc_graph, dependency_incremental = timed(lambda: vibe_core.dependency_graph(root))

        expected_edges = max(size - 1, 0)
        observed_edges = len(graph.get("edges") or [])
        validations = {
            "source_file_count_exact": context.get("source_file_count") == size,
            "dependency_node_count_exact": len(graph.get("nodes") or []) == size,
            "dependency_chain_complete": observed_edges == expected_edges,
            "context_cache_hit": (cached_context.get("cache") or {}).get("mode") == "CACHE_HIT",
            "dependency_cache_hit": (cached_graph.get("cache") or {}).get("mode") == "CACHE_HIT",
            "context_incremental": (inc_context.get("cache") or {}).get("mode") == "INCREMENTAL_REFRESH",
            "dependency_incremental": (inc_graph.get("cache") or {}).get("mode") == "INCREMENTAL_REFRESH",
        }
        failed = [name for name, passed in validations.items() if not passed]
        if failed:
            raise RuntimeError(
                "Benchmark fixture/runtime validation failed for {} files: {}".format(
                    size, ", ".join(failed)
                )
            )

        return {
            "size": size,
            "setup_seconds": setup_seconds,
            "context_rebuild_seconds": context_rebuild,
            "dependency_rebuild_seconds": dependency_rebuild,
            "context_cache_hit_seconds": context_hit,
            "dependency_cache_hit_seconds": dependency_hit,
            "retrieval_seconds": retrieval,
            "context_incremental_seconds": context_incremental,
            "dependency_incremental_seconds": dependency_incremental,
            "source_files": context.get("source_file_count"),
            "dependency_nodes": len(graph.get("nodes") or []),
            "dependency_edges": observed_edges,
            "expected_dependency_edges": expected_edges,
            "validations": validations,
            "retrieval_confidence": relevant.get("retrieval_confidence"),
            "retrieval_target_count": len(relevant.get("targets") or []),
            "incremental_context_mode": (inc_context.get("cache") or {}).get("mode"),
            "incremental_dependency_mode": (inc_graph.get("cache") or {}).get("mode"),
        }


def parse_args():
    parser = argparse.ArgumentParser(description="Benchmark my-vibe-kit runtime scaling.")
    parser.add_argument(
        "--sizes",
        nargs="+",
        type=int,
        default=[1000, 5000, 20000],
        help="Synthetic source-file counts. Defaults to 1000 5000 20000.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON only.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    results = [benchmark_size(size) for size in args.sizes]
    payload = {
        "benchmark": "synthetic-python-chain",
        "sizes": args.sizes,
        "results": results,
        "note": "Use the same machine/runtime for before-after comparisons; absolute times are environment-dependent.",
    }
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print("my-vibe-kit synthetic runtime benchmark")
        for result in results:
            print(
                "{size:>6} files | rebuild context {context_rebuild_seconds:>7.3f}s | "
                "deps {dependency_rebuild_seconds:>7.3f}s | cache {context_cache_hit_seconds:>7.3f}s | "
                "incremental {context_incremental_seconds:>7.3f}s/{dependency_incremental_seconds:>7.3f}s | "
                "retrieval {retrieval_seconds:>7.3f}s".format(**result)
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
