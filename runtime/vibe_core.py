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

from vibe_architecture import architecture_policy, default_architecture_config
from vibe_stacks import (
    detect_stack as detect_stack_extended,
    effective_adapter,
    framework_context,
    scan_polyglot_dependencies,
)
from vibe_state import (
    cache_status,
    current_repo_state,
    load_cache,
    state_summary as persistent_state_summary,
    write_cache,
)

IGNORE_DIRS = {
    ".git",
    ".vibe",
    ".agents",
    ".claude",
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
    "vendor",
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
    return str(result["stdout"]).rstrip("\r\n")


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
    data.setdefault("version", 3)
    data.setdefault("architecture", default_architecture_config())
    data.setdefault("context", {})
    data.setdefault("index", {})
    data.setdefault("dependency", {})
    data.setdefault("verification", {})
    data.setdefault("tasks", {})
    data["context"].setdefault("strategy", "persistent-incremental")
    data["context"].setdefault("max_dependency_depth", 2)
    data["context"].setdefault("max_files", 20000)
    data["context"].setdefault("max_source_files", 20)
    data["context"].setdefault("max_test_files", 10)
    data["context"].setdefault("max_related_modules", 8)
    data["index"].setdefault("backend", "json")
    data["index"].setdefault("use_git_delta", True)
    data["index"].setdefault("full_rebuild_on_schema_change", True)
    data["dependency"].setdefault("fail_on_new_cycles", True)
    data["verification"].setdefault("require_commands", True)
    data["verification"].setdefault("commands", [])
    data["tasks"].setdefault("keep_history", True)
    data["tasks"].setdefault("auto_load_history", False)
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
        or name.endswith("_test.go")
        or name.endswith("test.java")
        or name.endswith("tests.java")
        or ".test." in name
        or ".spec." in name
    )


MANIFEST_NAMES = {
    "pyproject.toml",
    "requirements.txt",
    "setup.py",
    "setup.cfg",
    "package.json",
    "tsconfig.json",
    "composer.json",
    "composer.lock",
    "Pipfile",
    "Cargo.toml",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "global.json",
}


def _file_record(root: Path, path: Path) -> Optional[Dict[str, object]]:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    if path.is_symlink() or ignored(path, root) or not path.exists() or not path.is_file():
        return None
    suffix = path.suffix.lower()
    return {
        "path": rel.as_posix(),
        "extension": suffix,
        "source": suffix in SOURCE_EXTENSIONS,
        "test": suffix in SOURCE_EXTENSIONS and is_test_file(rel),
        "manifest": path.name in MANIFEST_NAMES,
    }


def _full_file_index(root: Path, max_files: int) -> Dict[str, Dict[str, object]]:
    result = {}
    for path in iter_files(root, max_files=max_files):
        record = _file_record(root, path)
        if record:
            result[str(record["path"])] = record
    return result


def _incremental_file_index(
    root: Path,
    previous: Dict[str, object],
    changed_files: Sequence[str],
    max_files: int,
) -> Dict[str, Dict[str, object]]:
    result = {
        str(path): dict(value)
        for path, value in previous.items()
        if isinstance(path, str) and isinstance(value, dict)
    }
    for raw in changed_files:
        rel = Path(raw).as_posix()
        path = root / rel
        record = _file_record(root, path)
        if record is None:
            result.pop(rel, None)
        else:
            result[rel] = record
    if len(result) > max_files:
        result = {key: result[key] for key in sorted(result)[:max_files]}
    return result


def _component_item_file(item: object) -> Optional[str]:
    if isinstance(item, str):
        return item
    if isinstance(item, dict) and isinstance(item.get("file"), str):
        return str(item["file"])
    return None


def _merge_framework_context(
    root: Path,
    cached: Dict[str, object],
    changed_files: Sequence[str],
    all_source_paths: Sequence[str],
) -> Dict[str, object]:
    current_stack = detect_stack(root)
    current_frameworks = list(current_stack.get("frameworks") or [])
    cached_frameworks = list(cached.get("frameworks") or [])
    if current_frameworks != cached_frameworks or "django" in current_frameworks:
        files = [root / value for value in all_source_paths if (root / value).exists()]
        return framework_context(root, files)

    changed = {Path(value).as_posix() for value in changed_files}
    existing_changed = [
        root / value for value in changed
        if value in all_source_paths and (root / value).exists()
    ]
    partial = framework_context(root, existing_changed)

    routes = [
        item for item in (cached.get("routes") or [])
        if isinstance(item, dict) and item.get("file") not in changed
    ]
    routes.extend(partial.get("routes") or [])

    components = {}
    cached_components = cached.get("components") or {}
    partial_components = partial.get("components") or {}
    for key in set(cached_components) | set(partial_components):
        values = []
        for item in cached_components.get(key, []) or []:
            if _component_item_file(item) not in changed:
                values.append(item)
        values.extend(partial_components.get(key, []) or [])
        unique = []
        seen = set()
        for item in values:
            marker = json.dumps(item, sort_keys=True, ensure_ascii=False)
            if marker not in seen:
                seen.add(marker)
                unique.append(item)
        components[key] = unique

    return {
        "frameworks": current_frameworks,
        "routes": sorted(
            routes,
            key=lambda item: (
                str(item.get("framework", "")),
                str(item.get("file", "")),
                str(item.get("path", "")),
                str(item.get("method", "")),
            ),
        ),
        "components": components,
        "notes": partial.get("notes") or cached.get("notes") or [],
    }


def _materialize_context_bundle(
    root: Path,
    data: Dict[str, object],
    framework: Dict[str, object],
    adapter: Dict[str, object],
    architecture: Dict[str, object],
) -> None:
    json_dump(runtime_dir(root) / "project-map.json", data)
    json_dump(runtime_dir(root) / "framework-map.json", framework)
    json_dump(runtime_dir(root) / "active-adapter.json", adapter)
    json_dump(runtime_dir(root) / "architecture-policy.json", architecture)
    copy_to_current_task(root, "context.json", data)
    copy_to_current_task(root, "framework.json", framework)
    copy_to_current_task(root, "active-adapter.json", adapter)
    copy_to_current_task(root, "architecture-policy.json", architecture)


def project_context(root: Path, force: bool = False) -> Dict[str, object]:
    config = load_config(root)
    max_files = int(config["context"].get("max_files", 20000))
    refresh = cache_status(root, "context", force=force)

    if refresh["mode"] == "CACHE_HIT":
        cached = load_cache(root, "context", {})
        framework = load_cache(root, "framework", {})
        adapter = load_cache(root, "adapter", {})
        architecture = load_cache(root, "architecture", {})
        if all(isinstance(item, dict) for item in (cached, framework, adapter, architecture)):
            data = dict(cached)
            data["cache"] = {
                "mode": "CACHE_HIT",
                "reason": refresh["reason"],
                "changed_files": [],
            }
            _materialize_context_bundle(root, data, framework, adapter, architecture)
            return data
        refresh = {
            "mode": "FULL_REBUILD",
            "reason": "context-bundle-incomplete",
            "changed_files": [],
            "repo_state": current_repo_state(root),
        }

    previous_files = load_cache(root, "files", {})
    if refresh["mode"] == "INCREMENTAL_REFRESH" and isinstance(previous_files, dict):
        file_index = _incremental_file_index(
            root,
            previous_files,
            refresh["changed_files"],
            max_files,
        )
    else:
        refresh["mode"] = "FULL_REBUILD"
        file_index = _full_file_index(root, max_files)

    source_paths = sorted(
        path for path, item in file_index.items()
        if isinstance(item, dict) and item.get("source")
    )
    test_files = sorted(
        path for path, item in file_index.items()
        if isinstance(item, dict) and item.get("test")
    )
    manifests = sorted(
        path for path, item in file_index.items()
        if isinstance(item, dict) and item.get("manifest")
    )
    counts = defaultdict(int)
    for path in source_paths:
        counts[Path(path).suffix.lower()] += 1

    top_level = []
    try:
        top_level = sorted(
            item.name for item in root.iterdir()
            if item.is_dir() and item.name not in IGNORE_DIRS
        )
    except OSError:
        pass

    if refresh["mode"] == "INCREMENTAL_REFRESH":
        cached_framework = load_cache(root, "framework", {})
        if isinstance(cached_framework, dict):
            framework = _merge_framework_context(
                root,
                cached_framework,
                refresh["changed_files"],
                source_paths,
            )
        else:
            framework = framework_context(
                root,
                [root / path for path in source_paths if (root / path).exists()],
            )
    else:
        framework = framework_context(
            root,
            [root / path for path in source_paths if (root / path).exists()],
        )

    adapter = effective_adapter(root)
    architecture = architecture_policy(root, config, source_paths=source_paths)
    status_text = git(root, "status", "--short")
    branch = git(root, "branch", "--show-current")
    data = {
        "generated_at": utc_now(),
        "root": str(root),
        "stack": detect_stack(root),
        "frameworks": framework.get("frameworks", []),
        "framework_route_count": len(framework.get("routes", [])),
        "architecture": {
            "profile": architecture.get("effective_profile"),
            "pattern": architecture.get("pattern"),
            "module_style": architecture.get("module_style"),
        },
        "active_adapter": {
            "language": (adapter.get("language") or {}).get("id"),
            "frameworks": [
                item.get("id") for item in (adapter.get("frameworks") or [])
                if isinstance(item, dict)
            ],
        },
        "source_file_count": len(source_paths),
        "source_extensions": dict(sorted(counts.items())),
        "manifests": manifests,
        "test_files": test_files,
        "top_level_directories": top_level,
        "git": {
            "branch": branch,
            "dirty": bool(status_text),
            "status": status_text.splitlines() if status_text else [],
        },
        "cache": {
            "mode": refresh["mode"],
            "reason": refresh["reason"],
            "changed_files": list(refresh["changed_files"]),
        },
    }

    repo_state = refresh["repo_state"]
    write_cache(root, "files", file_index, repo_state)
    write_cache(root, "framework", framework, repo_state)
    write_cache(root, "adapter", adapter, repo_state)
    write_cache(root, "architecture", architecture, repo_state)
    write_cache(root, "context", data, repo_state)
    _materialize_context_bundle(root, data, framework, adapter, architecture)
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


def scan_python_dependency_sources(
    root: Path,
    source_files: Sequence[Path],
    universe_files: Sequence[Path],
) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    python_files = [path for path in universe_files if path.suffix == ".py"]
    source_python_files = [path for path in source_files if path.suffix == ".py"]
    module_to_path = {}
    path_to_module = {}
    for path in python_files:
        try:
            rel = path.relative_to(root)
        except ValueError:
            continue
        module = python_module_name(rel)
        if module:
            rel_text = rel.as_posix()
            module_to_path[module] = rel_text
            path_to_module[rel_text] = module

    nodes = set()
    edges = set()
    for path in source_python_files:
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        nodes.add(rel)
        current_module = path_to_module.get(rel, python_module_name(Path(rel)))
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


def scan_python_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    return scan_python_dependency_sources(root, files, files)

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


def _dependency_payload(
    root: Path,
    nodes: Set[str],
    edges: Set[Tuple[str, str]],
    stack: Dict[str, object],
    cache_meta: Dict[str, object],
) -> Dict[str, object]:
    reverse = defaultdict(list)
    adjacency = defaultdict(list)
    for source, target in sorted(edges):
        adjacency[source].append(target)
        reverse[target].append(source)

    suffixes = {Path(node).suffix.lower() for node in nodes}
    scanners = []
    if ".py" in suffixes:
        scanners.append("python-ast")
    if suffixes & {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}:
        scanners.append("javascript-typescript-relative-imports")
    if ".php" in suffixes:
        scanners.append("php-static")
    if suffixes & {".java", ".kt", ".kts"}:
        scanners.append("java-kotlin-imports")
    if ".go" in suffixes:
        scanners.append("go-module-imports")
    if ".rs" in suffixes:
        scanners.append("rust-mod-use")

    return {
        "generated_at": utc_now(),
        "stack": stack,
        "scanners": scanners or ["project-map-only"],
        "nodes": sorted(nodes),
        "edges": [{"from": source, "to": target} for source, target in sorted(edges)],
        "dependencies": {key: sorted(values) for key, values in sorted(adjacency.items())},
        "reverse_dependencies": {key: sorted(values) for key, values in sorted(reverse.items())},
        "cycles": strongly_connected_components(nodes, edges),
        "limitations": [
            "Static baseline only: dynamic imports, runtime dependency injection, reflection, generated code, framework registries, macros, and non-relative JS/TS aliases may require native analyzers.",
            "Incremental refresh is file-level for Python/JavaScript/TypeScript; PHP/Java/Kotlin/Go/Rust refresh only the affected language slice when those files or their module manifest change.",
        ],
        "primary_language": stack.get("primary"),
        "cache": cache_meta,
    }


def dependency_graph(root: Path, force: bool = False) -> Dict[str, object]:
    project_context(root, force=force)
    refresh = cache_status(root, "dependency", force=force)
    if refresh["mode"] == "CACHE_HIT":
        cached = load_cache(root, "dependency", {})
        if isinstance(cached, dict):
            data = dict(cached)
            data["cache"] = {
                "mode": "CACHE_HIT",
                "reason": refresh["reason"],
                "changed_files": [],
            }
            json_dump(runtime_dir(root) / "dependency-map.json", data)
            return data
        refresh = {
            "mode": "FULL_REBUILD",
            "reason": "dependency-cache-invalid",
            "changed_files": [],
            "repo_state": current_repo_state(root),
        }

    file_index = load_cache(root, "files", {})
    if not isinstance(file_index, dict):
        project_context(root, force=True)
        file_index = load_cache(root, "files", {})

    source_paths = sorted(
        path for path, item in file_index.items()
        if isinstance(item, dict) and item.get("source")
    )
    all_files = [root / path for path in source_paths if (root / path).exists()]
    stack = detect_stack(root)

    if refresh["mode"] == "INCREMENTAL_REFRESH":
        previous = load_cache(root, "dependency", {})
    else:
        previous = {}

    if refresh["mode"] == "INCREMENTAL_REFRESH" and isinstance(previous, dict):
        nodes = set(str(item) for item in (previous.get("nodes") or []))
        edges = edge_set(previous)
        changed = {Path(item).as_posix() for item in refresh["changed_files"]}
        current_sources = set(source_paths)
        deleted = {path for path in changed if path in nodes and path not in current_sources}
        changed_current = {path for path in changed if path in current_sources}

        edges = {
            (source, target) for source, target in edges
            if source not in changed_current
            and source not in deleted
            and target not in deleted
        }
        nodes.difference_update(deleted)
        nodes.update(changed_current)

        python_changed = [
            root / path for path in changed_current if Path(path).suffix.lower() == ".py"
        ]
        if python_changed:
            py_nodes, py_edges = scan_python_dependency_sources(
                root,
                python_changed,
                [root / path for path in source_paths if Path(path).suffix.lower() == ".py"],
            )
            nodes.update(py_nodes)
            edges.update(py_edges)

        js_ext = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
        js_changed = [
            root / path for path in changed_current if Path(path).suffix.lower() in js_ext
        ]
        if js_changed:
            js_nodes, js_edges = scan_js_dependencies(root, js_changed)
            nodes.update(js_nodes)
            edges.update(js_edges)

        language_groups = [
            ({".php"}, {"composer.json", "composer.lock"}),
            ({".java", ".kt", ".kts"}, {"pom.xml", "build.gradle", "build.gradle.kts"}),
            ({".go"}, {"go.mod"}),
            ({".rs"}, {"Cargo.toml"}),
        ]
        for extensions, manifests in language_groups:
            needs_refresh = any(Path(path).suffix.lower() in extensions for path in changed)
            needs_refresh = needs_refresh or any(Path(path).name in manifests for path in changed)
            if not needs_refresh:
                continue
            old_group = {node for node in nodes if Path(node).suffix.lower() in extensions}
            nodes.difference_update(old_group)
            edges = {
                (source, target) for source, target in edges
                if source not in old_group and target not in old_group
            }
            group_files = [
                root / path for path in source_paths if Path(path).suffix.lower() in extensions
            ]
            extra_nodes, extra_edges, _ = scan_polyglot_dependencies(root, group_files)
            nodes.update(extra_nodes)
            edges.update(extra_edges)

        cache_meta = {
            "mode": "INCREMENTAL_REFRESH",
            "reason": refresh["reason"],
            "changed_files": sorted(changed),
        }
    else:
        nodes = set()
        edges = set()
        python_nodes, python_edges = scan_python_dependencies(root, all_files)
        nodes.update(python_nodes)
        edges.update(python_edges)
        js_nodes, js_edges = scan_js_dependencies(root, all_files)
        nodes.update(js_nodes)
        edges.update(js_edges)
        extra_nodes, extra_edges, _ = scan_polyglot_dependencies(root, all_files)
        nodes.update(extra_nodes)
        edges.update(extra_edges)
        cache_meta = {
            "mode": "FULL_REBUILD",
            "reason": refresh["reason"],
            "changed_files": list(refresh["changed_files"]),
        }

    data = _dependency_payload(root, nodes, edges, stack, cache_meta)
    json_dump(runtime_dir(root) / "dependency-map.json", data)
    write_cache(root, "dependency", data, refresh["repo_state"])
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


def bounded_dependencies(
    seeds: Sequence[str],
    dependencies: Dict[str, Sequence[str]],
    depth: int,
) -> List[str]:
    queue = deque((seed, 0) for seed in seeds)
    seen = set(seeds)
    result = set()
    while queue:
        node, current_depth = queue.popleft()
        if current_depth >= depth:
            continue
        for child in dependencies.get(node, []):
            if child in seen:
                continue
            seen.add(child)
            result.add(child)
            queue.append((child, current_depth + 1))
    return sorted(result)


def _query_tokens(value: str) -> List[str]:
    stop = {
        "add", "build", "change", "create", "fix", "implement", "refactor", "the",
        "this", "that", "with", "from", "into", "for", "and", "use", "using",
        "feature", "bug", "project", "task", "new",
    }
    return [
        token for token in re.findall(r"[A-Za-z0-9_]+", value.lower())
        if len(token) >= 3 and token not in stop
    ]


def _path_score(path: str, tokens: Sequence[str]) -> int:
    lowered = path.lower()
    stem = Path(path).stem.lower()
    score = 0
    for token in tokens:
        if token == stem:
            score += 6
        elif token in stem:
            score += 4
        elif token in lowered:
            score += 2
    return score


def relevant_context(
    root: Path,
    targets: Optional[Sequence[str]] = None,
    query: Optional[str] = None,
) -> Dict[str, object]:
    context = project_context(root)
    graph = dependency_graph(root)
    config = load_config(root)
    context_config = config.get("context") or {}
    depth = int(context_config.get("max_dependency_depth", 2))
    max_source = int(context_config.get("max_source_files", 20))
    max_tests = int(context_config.get("max_test_files", 10))
    max_modules = int(context_config.get("max_related_modules", 8))

    nodes = [str(item) for item in (graph.get("nodes") or [])]
    test_files = set(str(item) for item in (context.get("test_files") or []))
    selected = [
        Path(item).as_posix() for item in (targets or [])
        if Path(item).as_posix() in set(nodes)
    ]

    if not selected:
        selected = [path for path in changed_files(root) if path in set(nodes)]

    active_query = query or ""
    task = current_task(root)
    if not active_query and isinstance(task, dict):
        active_query = str(task.get("request") or "")

    tokens = _query_tokens(active_query)
    if not selected and tokens:
        ranked = sorted(
            (
                (_path_score(path, tokens), path)
                for path in nodes
                if path not in test_files
            ),
            key=lambda item: (-item[0], item[1]),
        )
        selected = [path for score, path in ranked if score > 0][:3]

    dependencies = graph.get("dependencies") or {}
    reverse = graph.get("reverse_dependencies") or {}
    forward = bounded_dependencies(selected, dependencies, depth)
    consumers = bounded_reverse_dependencies(selected, reverse, depth)
    ordered = []
    for path in list(selected) + forward + consumers:
        if path not in ordered:
            ordered.append(path)

    source_files = [path for path in ordered if path not in test_files][:max_source]
    impacted = set(source_files) | set(selected)
    related_tests = []
    for test in sorted(test_files):
        deps = set(dependencies.get(test, []))
        score = _path_score(test, tokens)
        if test in impacted or deps & impacted or score > 0:
            related_tests.append(test)
    related_tests = related_tests[:max_tests]

    modules = []
    for path in source_files:
        parts = Path(path).parts
        if not parts:
            continue
        if parts[0] in {"src", "app", "lib", "internal", "packages", "apps"} and len(parts) > 1:
            module = "/".join(parts[:2])
        else:
            module = parts[0]
        if module not in modules:
            modules.append(module)
        if len(modules) >= max_modules:
            break

    data = {
        "generated_at": utc_now(),
        "query": active_query,
        "query_tokens": tokens,
        "targets": selected,
        "source_files": source_files,
        "test_files": related_tests,
        "related_modules": modules,
        "dependency_depth": depth,
        "limits": {
            "max_source_files": max_source,
            "max_test_files": max_tests,
            "max_related_modules": max_modules,
        },
        "history_policy": {
            "auto_load_history": bool((config.get("tasks") or {}).get("auto_load_history", False)),
            "note": "Historical task folders are cold storage and are not loaded automatically.",
        },
    }
    json_dump(runtime_dir(root) / "relevant-context.json", data)
    copy_to_current_task(root, "relevant-context.json", data)
    return data


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
    framework_map = json_load(runtime_dir(root) / "framework-map.json", None)
    if not isinstance(framework_map, dict):
        project_context(root)
        framework_map = json_load(runtime_dir(root) / "framework-map.json", {})
    affected_routes = [
        route for route in (framework_map.get("routes") or [])
        if isinstance(route, dict) and route.get("file") in impacted_set
    ]

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
        "affected_routes": affected_routes,
        "frameworks": framework_map.get("frameworks", []) if isinstance(framework_map, dict) else [],
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

    architecture = json_load(runtime_dir(root) / "architecture-policy.json", {})
    data = {
        "generated_at": utc_now(),
        "status": status,
        "architecture": {
            "profile": architecture.get("effective_profile") if isinstance(architecture, dict) else None,
            "pattern": architecture.get("pattern") if isinstance(architecture, dict) else None,
            "module_style": architecture.get("module_style") if isinstance(architecture, dict) else None,
        },
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
        "persistent_state": persistent_state_summary(root),
        "runtime": {
            "project_map": (runtime_dir(root) / "project-map.json").exists(),
            "architecture_policy": (runtime_dir(root) / "architecture-policy.json").exists(),
            "dependency_map": (runtime_dir(root) / "dependency-map.json").exists(),
            "relevant_context": (runtime_dir(root) / "relevant-context.json").exists(),
            "impact": (runtime_dir(root) / "impact.json").exists(),
            "verification": (runtime_dir(root) / "verification.json").exists(),
        },
    }
