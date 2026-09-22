"""Deterministic repository context, dependency, impact, task, and verification helpers."""

import ast
import json
import os
import re
import shutil
import subprocess
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from vibe_stacks import (
    detect_stack as detect_stack_extended,
    framework_context,
    scan_polyglot_dependencies,
)

IGNORE_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".tox",
    ".nox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".next",
    ".nuxt",
    "target",
}
SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".kts",
    ".cs",
    ".rb",
    ".php",
}
TEST_HINTS = ("test", "tests", "spec", "specs", "__tests__")
JS_IMPORT_RE = re.compile(
    r"""(?:import\s+(?:[^'"]+?\s+from\s+)?|export\s+[^'"]*?\s+from\s+|require\s*\(|import\s*\()\s*['"]([^'"]+)['"]"""
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def json_dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def json_load(path: Path, default: object = None) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def run_process(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 900,
    max_output: int = 20000,
) -> Dict[str, object]:
    started = time.monotonic()
    try:
        proc = subprocess.run(
            list(command),
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        return {
            "command": list(command),
            "returncode": proc.returncode,
            "stdout": proc.stdout[-max_output:],
            "stderr": proc.stderr[-max_output:],
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except FileNotFoundError as exc:
        return {
            "command": list(command),
            "returncode": 127,
            "stdout": "",
            "stderr": str(exc),
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return {
            "command": list(command),
            "returncode": 124,
            "stdout": str(stdout)[-max_output:],
            "stderr": ("Timed out. " + str(stderr))[-max_output:],
            "duration_seconds": round(time.monotonic() - started, 3),
        }


def git(root: Path, *args: str) -> Optional[str]:
    result = run_process(["git"] + list(args), cwd=root, timeout=60)
    if result["returncode"] != 0:
        return None
    return str(result["stdout"]).strip()


def repository_root(start: Path) -> Path:
    start = start.resolve()
    value = git(start, "rev-parse", "--show-toplevel")
    if value:
        return Path(value).resolve()
    return start


def runtime_dir(root: Path) -> Path:
    return root / ".vibe" / "runtime"


def tasks_dir(root: Path) -> Path:
    return root / ".vibe" / "tasks"


def config_path(root: Path) -> Path:
    return root / ".vibe" / "config.json"


def load_config(root: Path) -> Dict[str, object]:
    data = json_load(config_path(root), {})
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", 1)
    data.setdefault("context", {})
    data.setdefault("dependency", {})
    data.setdefault("verification", {})
    data.setdefault("tasks", {})
    data["context"].setdefault("max_dependency_depth", 3)
    data["context"].setdefault("max_files", 20000)
    data["dependency"].setdefault("fail_on_new_cycles", True)
    data["verification"].setdefault("require_commands", True)
    data["verification"].setdefault("commands", [])
    data["tasks"].setdefault("keep_history", True)
    return data


def detect_stack(root: Path) -> Dict[str, object]:
    return detect_stack_extended(root)

def ignored(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    return any(part in IGNORE_DIRS for part in rel.parts)


def iter_files(root: Path, max_files: int = 20000) -> Iterable[Path]:
    count = 0
    for current, dirs, filenames in os.walk(str(root)):
        current_path = Path(current)
        dirs[:] = [
            name
            for name in dirs
            if name not in IGNORE_DIRS and not (current_path / name).is_symlink()
        ]
        for filename in filenames:
            path = current_path / filename
            if path.is_symlink() or ignored(path, root):
                continue
            yield path
            count += 1
            if count >= max_files:
                return


def is_test_file(path: Path) -> bool:
    lowered_parts = [part.lower() for part in path.parts]
    name = path.name.lower()
    return (
        any(part in TEST_HINTS for part in lowered_parts)
        or name.startswith("test_")
        or name.endswith("_test.py")
        or ".test." in name
        or ".spec." in name
    )


def project_context(root: Path) -> Dict[str, object]:
    config = load_config(root)
    max_files = int(config["context"].get("max_files", 20000))
    files = list(iter_files(root, max_files=max_files))
    counts = defaultdict(int)
    source_files = []
    test_files = []
    manifests = []
    manifest_names = {
        "pyproject.toml",
        "requirements.txt",
        "setup.py",
        "setup.cfg",
        "package.json",
        "tsconfig.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
        "global.json",
    }

    for path in files:
        rel = path.relative_to(root).as_posix()
        if path.suffix.lower() in SOURCE_EXTENSIONS:
            counts[path.suffix.lower()] += 1
            source_files.append(rel)
            if is_test_file(path.relative_to(root)):
                test_files.append(rel)
        if path.name in manifest_names:
            manifests.append(rel)

    top_level = []
    try:
        top_level = sorted(
            item.name for item in root.iterdir()
            if item.is_dir() and item.name not in IGNORE_DIRS
        )
    except OSError:
        pass

    status = git(root, "status", "--short")
    branch = git(root, "branch", "--show-current")
    framework = framework_context(root, files)

    data = {
        "generated_at": utc_now(),
        "root": str(root),
        "stack": detect_stack(root),
        "frameworks": framework.get("frameworks", []),
        "framework_route_count": len(framework.get("routes", [])),
        "source_file_count": len(source_files),
        "source_extensions": dict(sorted(counts.items())),
        "manifests": sorted(manifests),
        "test_files": sorted(test_files),
        "top_level_directories": top_level,
        "git": {
            "branch": branch,
            "dirty": bool(status),
            "status": status.splitlines() if status else [],
        },
    }
    json_dump(runtime_dir(root) / "project-map.json", data)
    json_dump(runtime_dir(root) / "framework-map.json", framework)
    copy_to_current_task(root, "context.json", data)
    copy_to_current_task(root, "framework.json", framework)
    return data


def python_module_name(rel: Path) -> str:
    parts = list(rel.with_suffix("").parts)
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def best_python_target(module: str, module_to_path: Dict[str, str]) -> Optional[str]:
    candidate = module
    while candidate:
        if candidate in module_to_path:
            return module_to_path[candidate]
        candidate = candidate.rpartition(".")[0]
    return None


def resolve_relative_python(
    current_module: str,
    level: int,
    module: Optional[str],
    *,
    is_package: bool = False,
) -> str:
    package_parts = current_module.split(".") if is_package else current_module.split(".")[:-1]
    if level > 0:
        trim = max(level - 1, 0)
        if trim:
            package_parts = package_parts[:-trim] if trim <= len(package_parts) else []
    if module:
        package_parts.extend(module.split("."))
    return ".".join(part for part in package_parts if part)


def scan_python_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    python_files = [path for path in files if path.suffix == ".py"]
    module_to_path = {}
    path_to_module = {}
    for path in python_files:
        rel = path.relative_to(root)
        module = python_module_name(rel)
        if module:
            rel_text = rel.as_posix()
            module_to_path[module] = rel_text
            path_to_module[rel_text] = module

    nodes = set(path_to_module)
    edges = set()

    for path in python_files:
        rel = path.relative_to(root).as_posix()
        current_module = path_to_module.get(rel, "")
        try:
            text = path.read_text(encoding="utf-8")
            tree = ast.parse(text, filename=str(path))
        except (OSError, UnicodeDecodeError, SyntaxError):
            continue

        for node in ast.walk(tree):
            targets = []
            if isinstance(node, ast.Import):
                targets.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    base = resolve_relative_python(
                        current_module,
                        node.level,
                        node.module,
                        is_package=path.name == "__init__.py",
                    )
                else:
                    base = node.module or ""
                if base:
                    targets.append(base)
                    for alias in node.names:
                        if alias.name != "*":
                            targets.append(base + "." + alias.name)

            resolved = None
            for target in targets:
                resolved = best_python_target(target, module_to_path)
                if resolved:
                    break
            if resolved and resolved != rel:
                edges.add((rel, resolved))

    return nodes, edges


def resolve_js_target(source: Path, spec: str, root: Path) -> Optional[str]:
    if not spec.startswith("."):
        return None
    base = (source.parent / spec).resolve()
    candidates = []
    if base.suffix:
        candidates.append(base)
    else:
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            candidates.append(Path(str(base) + ext))
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            candidates.append(base / ("index" + ext))

    for candidate in candidates:
        try:
            rel = candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.exists() and candidate.is_file():
            return rel.as_posix()
    return None


def scan_js_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    js_ext = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
    js_files = [path for path in files if path.suffix.lower() in js_ext]
    nodes = {path.relative_to(root).as_posix() for path in js_files}
    edges = set()
    for path in js_files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in JS_IMPORT_RE.finditer(text):
            target = resolve_js_target(path, match.group(1), root)
            if target and target != rel:
                edges.add((rel, target))
    return nodes, edges


def strongly_connected_components(nodes: Iterable[str], edges: Iterable[Tuple[str, str]]) -> List[List[str]]:
    adjacency = defaultdict(list)
    for source, target in edges:
        adjacency[source].append(target)

    index = 0
    indices = {}
    lowlinks = {}
    stack = []
    on_stack = set()
    components = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = index
        lowlinks[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)

        for target in adjacency.get(node, []):
            if target not in indices:
                visit(target)
                lowlinks[node] = min(lowlinks[node], lowlinks[target])
            elif target in on_stack:
                lowlinks[node] = min(lowlinks[node], indices[target])

        if lowlinks[node] == indices[node]:
            component = []
            while stack:
                value = stack.pop()
                on_stack.remove(value)
                component.append(value)
                if value == node:
                    break
            if len(component) > 1:
                components.append(sorted(component))

    for node in sorted(set(nodes)):
        if node not in indices:
            visit(node)

    return sorted(components)


def dependency_graph(root: Path) -> Dict[str, object]:
    config = load_config(root)
    max_files = int(config["context"].get("max_files", 20000))
    all_files = list(iter_files(root, max_files=max_files))
    stack = detect_stack(root)
    primary = stack["primary"]

    nodes = set()
    edges = set()
    scanners = []

    python_nodes, python_edges = scan_python_dependencies(root, all_files)
    if python_nodes:
        nodes.update(python_nodes)
        edges.update(python_edges)
        scanners.append("python-ast")

    js_nodes, js_edges = scan_js_dependencies(root, all_files)
    if js_nodes:
        nodes.update(js_nodes)
        edges.update(js_edges)
        scanners.append("javascript-typescript-relative-imports")

    extra_nodes, extra_edges, extra_scanners = scan_polyglot_dependencies(root, all_files)
    if extra_nodes:
        nodes.update(extra_nodes)
        edges.update(extra_edges)
        scanners.extend(extra_scanners)

    reverse = defaultdict(list)
    adjacency = defaultdict(list)
    for source, target in sorted(edges):
        adjacency[source].append(target)
        reverse[target].append(source)

    data = {
        "generated_at": utc_now(),
        "stack": stack,
        "scanners": scanners or ["project-map-only"],
        "nodes": sorted(nodes),
        "edges": [{"from": source, "to": target} for source, target in sorted(edges)],
        "dependencies": {key: sorted(values) for key, values in sorted(adjacency.items())},
        "reverse_dependencies": {key: sorted(values) for key, values in sorted(reverse.items())},
        "cycles": strongly_connected_components(nodes, edges),
        "limitations": [
            "Static baseline only: dynamic imports, runtime dependency injection, reflection, generated code, framework registries, macros, and non-relative JS/TS aliases may require native analyzers."
        ],
        "primary_language": primary,
    }
    json_dump(runtime_dir(root) / "dependency-map.json", data)
    return data


def changed_files(root: Path) -> List[str]:
    status = git(root, "status", "--porcelain=v1")
    if not status:
        return []
    output = []
    for line in status.splitlines():
        if len(line) < 4:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        output.append(path.strip())
    return sorted(set(output))


def bounded_reverse_dependencies(
    seeds: Sequence[str],
    reverse: Dict[str, Sequence[str]],
    depth: int,
) -> List[str]:
    queue = deque((seed, 0) for seed in seeds)
    seen = set(seeds)
    result = set()
    while queue:
        node, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for parent in reverse.get(node, []):
            if parent in seen:
                continue
            seen.add(parent)
            result.add(parent)
            queue.append((parent, current_depth + 1))
    return sorted(result)


def impact_analysis(root: Path, targets: Optional[Sequence[str]] = None) -> Dict[str, object]:
    graph_path = runtime_dir(root) / "dependency-map.json"
    graph = json_load(graph_path, None)
    if not isinstance(graph, dict):
        graph = dependency_graph(root)

    selected = list(targets or changed_files(root))
    selected = [Path(item).as_posix() for item in selected]
    reverse = graph.get("reverse_dependencies") or {}
    dependencies = graph.get("dependencies") or {}
    config = load_config(root)
    depth = int(config["context"].get("max_dependency_depth", 3))
    affected = bounded_reverse_dependencies(selected, reverse, depth)

    tests = []
    all_test_files = []
    context = json_load(runtime_dir(root) / "project-map.json", None)
    if isinstance(context, dict):
        all_test_files = list(context.get("test_files") or [])
    if not all_test_files:
        context = project_context(root)
        all_test_files = list(context.get("test_files") or [])

    impacted_set = set(selected) | set(affected)
    for test in all_test_files:
        if test in impacted_set:
            tests.append(test)
            continue
        deps = set(dependencies.get(test, []))
        if deps & impacted_set:
            tests.append(test)
            continue
        test_stem = Path(test).stem.replace("test_", "").replace("_test", "")
        if test_stem and any(test_stem in Path(item).stem for item in selected):
            tests.append(test)

    direct_dependencies = {
        item: sorted(dependencies.get(item, []))
        for item in selected
        if dependencies.get(item)
    }
    direct_consumers = {
        item: sorted(reverse.get(item, []))
        for item in selected
        if reverse.get(item)
    }

    data = {
        "generated_at": utc_now(),
        "targets": selected,
        "direct_dependencies": direct_dependencies,
        "direct_consumers": direct_consumers,
        "affected_reverse_dependencies": affected,
        "affected_tests": sorted(set(tests)),
        "depth": depth,
    }
    json_dump(runtime_dir(root) / "impact.json", data)
    copy_to_current_task(root, "impact.json", data)
    return data


def slugify(value: str, limit: int = 48) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return (slug or "task")[:limit].rstrip("-")


def start_task(root: Path, mode: str, request: str) -> Dict[str, object]:
    valid_modes = {"feature", "change", "bug_fix", "refactor", "hotfix"}
    if mode not in valid_modes:
        raise ValueError("Unsupported mode: {}".format(mode))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    task_id = "{}-{}-{}".format(stamp, mode.replace("_", "-"), slugify(request))
    task_path = tasks_dir(root) / task_id
    task_path.mkdir(parents=True, exist_ok=True)
    task = {
        "id": task_id,
        "mode": mode,
        "request": request,
        "created_at": utc_now(),
        "path": str(task_path.relative_to(root)),
    }
    json_dump(task_path / "task.json", task)
    (task_path / "request.md").write_text(request.strip() + "\n", encoding="utf-8")
    json_dump(runtime_dir(root) / "current-task.json", task)
    return task


def current_task(root: Path) -> Optional[Dict[str, object]]:
    data = json_load(runtime_dir(root) / "current-task.json", None)
    return data if isinstance(data, dict) else None


def current_task_path(root: Path) -> Optional[Path]:
    task = current_task(root)
    if not task:
        return None
    relative = task.get("path")
    if not isinstance(relative, str):
        return None
    return root / relative


def copy_to_current_task(root: Path, filename: str, data: object) -> None:
    path = current_task_path(root)
    if path:
        json_dump(path / filename, data)


def snapshot_dependencies(root: Path, when: str) -> Dict[str, object]:
    if when not in {"before", "after"}:
        raise ValueError("Snapshot must be before or after")
    graph = json_load(runtime_dir(root) / "dependency-map.json", None)
    if not isinstance(graph, dict):
        graph = dependency_graph(root)
    task_path = current_task_path(root)
    if not task_path:
        raise RuntimeError("No current task. Start one before taking a snapshot.")
    destination = task_path / ("dependency-{}.json".format(when))
    json_dump(destination, graph)
    if when == "after":
        diff = dependency_diff(root)
        json_dump(task_path / "dependency-diff.json", diff)
        json_dump(runtime_dir(root) / "dependency-diff.json", diff)
    return graph


def edge_set(graph: Dict[str, object]) -> Set[Tuple[str, str]]:
    edges = set()
    for item in graph.get("edges") or []:
        if isinstance(item, dict) and "from" in item and "to" in item:
            edges.add((str(item["from"]), str(item["to"])))
    return edges


def cycle_set(graph: Dict[str, object]) -> Set[Tuple[str, ...]]:
    cycles = set()
    for item in graph.get("cycles") or []:
        if isinstance(item, list):
            cycles.add(tuple(sorted(str(value) for value in item)))
    return cycles


def dependency_diff(root: Path) -> Dict[str, object]:
    task_path = current_task_path(root)
    if not task_path:
        raise RuntimeError("No current task.")
    before = json_load(task_path / "dependency-before.json", {})
    after = json_load(task_path / "dependency-after.json", {})
    if not isinstance(before, dict):
        before = {}
    if not isinstance(after, dict):
        after = {}

    before_edges = edge_set(before)
    after_edges = edge_set(after)
    before_cycles = cycle_set(before)
    after_cycles = cycle_set(after)

    return {
        "generated_at": utc_now(),
        "added_edges": [
            {"from": source, "to": target}
            for source, target in sorted(after_edges - before_edges)
        ],
        "removed_edges": [
            {"from": source, "to": target}
            for source, target in sorted(before_edges - after_edges)
        ],
        "new_cycles": [list(item) for item in sorted(after_cycles - before_cycles)],
        "removed_cycles": [list(item) for item in sorted(before_cycles - after_cycles)],
        "before_nodes": len(before.get("nodes") or []),
        "after_nodes": len(after.get("nodes") or []),
    }


def verify(root: Path) -> Dict[str, object]:
    project_context(root)
    dependency_graph(root)

    task_path = current_task_path(root)
    dep_diff = None
    if task_path and (task_path / "dependency-before.json").exists():
        snapshot_dependencies(root, "after")
        dep_diff = json_load(task_path / "dependency-diff.json", {})

    config = load_config(root)
    verification = config.get("verification") or {}
    commands = verification.get("commands") or []
    require_commands = bool(verification.get("require_commands", True))
    results = []

    for command in commands:
        if not isinstance(command, list) or not command or not all(isinstance(x, str) for x in command):
            results.append(
                {
                    "command": command,
                    "returncode": 2,
                    "stdout": "",
                    "stderr": "Invalid command configuration; expected a non-empty list of strings.",
                    "duration_seconds": 0,
                }
            )
            continue
        results.append(run_process(command, cwd=root))

    failed_commands = [item for item in results if item.get("returncode") != 0]
    fail_on_new_cycles = bool((config.get("dependency") or {}).get("fail_on_new_cycles", True))
    new_cycles = []
    if isinstance(dep_diff, dict):
        new_cycles = dep_diff.get("new_cycles") or []

    if require_commands and not commands:
        status = "NEEDS_VERIFICATION_CONFIG"
    elif failed_commands or (fail_on_new_cycles and new_cycles):
        status = "FAIL_VERIFICATION"
    else:
        status = "PASS_VERIFIED"

    data = {
        "generated_at": utc_now(),
        "status": status,
        "require_commands": require_commands,
        "commands_configured": len(commands),
        "commands_run": len(results),
        "command_results": results,
        "dependency_diff": dep_diff,
        "new_cycles": new_cycles,
        "git_status": (git(root, "status", "--short") or "").splitlines(),
        "git_diff_stat": git(root, "diff", "--stat"),
    }
    json_dump(runtime_dir(root) / "verification.json", data)
    copy_to_current_task(root, "verification.json", data)
    return data


def status(root: Path) -> Dict[str, object]:
    return {
        "root": str(root),
        "task": current_task(root),
        "stack": detect_stack(root),
        "runtime": {
            "project_map": (runtime_dir(root) / "project-map.json").exists(),
            "dependency_map": (runtime_dir(root) / "dependency-map.json").exists(),
            "impact": (runtime_dir(root) / "impact.json").exists(),
            "verification": (runtime_dir(root) / "verification.json").exists(),
        },
    }
