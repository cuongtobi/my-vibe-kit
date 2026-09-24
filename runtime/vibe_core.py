"""Deterministic repository context, dependency, impact, task, and verification helpers."""

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections import defaultdict
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
from vibe_retrieval import (
    bounded_reverse_dependencies,
    build_relevant_payload,
    source_search_metadata,
)
from vibe_tasks import (
    copy_to_current_task,
    current_task,
    current_task_path,
    start_task,
)
from vibe_state import (
    cache_status,
    content_hash_index,
    current_repo_state,
    load_cache,
    repository_files,
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
    ".vue",
    ".svelte",
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return default


def run_process(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout: int = 900,
    max_output: int = 20000,
) -> Dict[str, object]:
    started = time.monotonic()
    resolved_command = list(command)
    if resolved_command:
        executable = Path(resolved_command[0])
        relative_path = any(separator in resolved_command[0] for separator in ("/", "\\"))
        lookup = str(cwd / executable) if relative_path and not executable.is_absolute() else str(executable)
        resolved_command[0] = shutil.which(lookup) or resolved_command[0]
    try:
        proc = subprocess.run(
            resolved_command,
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
    data["context"].setdefault("retrieval", {})
    retrieval = data["context"]["retrieval"]
    if not isinstance(retrieval, dict):
        retrieval = {}
        data["context"]["retrieval"] = retrieval
    retrieval.setdefault("min_index_score", 6)
    retrieval.setdefault("fallback_max_scan_files", 20000)
    retrieval.setdefault("fallback_read_bytes", 131072)
    retrieval.setdefault("query_aliases", {})
    data["index"].setdefault("backend", "json")
    data["index"].setdefault("use_git_delta", True)
    data["index"].setdefault("full_rebuild_on_schema_change", True)
    data["dependency"].setdefault("fail_on_new_cycles", True)
    data["verification"].setdefault("require_commands", True)
    data["verification"].setdefault("commands", [])
    if data["tasks"].get("keep_history") is False:
        raise RuntimeError("tasks.keep_history=false is unsupported. Remove this setting; task records are always retained.")
    data["tasks"].setdefault("auto_load_history", False)
    data["tasks"].setdefault("retention", {})
    retention = data["tasks"]["retention"]
    if not isinstance(retention, dict):
        retention = {}
        data["tasks"]["retention"] = retention
    retention.setdefault("policy", "bounded")
    retention.setdefault("max_tasks", 100)
    retention.setdefault("max_age_days", 90)
    retention.setdefault("cleanup", "manual")
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
    git_files = repository_files(root)
    if git_files is not None:
        for relative in git_files:
            path = root / relative
            if path.is_file() and not path.is_symlink() and not ignored(path, root):
                yield path
                count += 1
                if count >= max_files:
                    return
        return
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
    "pnpm-workspace.yaml",
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
    "Gemfile",
    "Gemfile.lock",
    "Rakefile",
}


def _file_record(root: Path, path: Path) -> Optional[Dict[str, object]]:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return None
    if path.is_symlink() or ignored(path, root) or not path.exists() or not path.is_file():
        return None
    suffix = path.suffix.lower()
    source = suffix in SOURCE_EXTENSIONS
    record = {
        "path": rel.as_posix(),
        "extension": suffix,
        "source": source,
        "test": source and is_test_file(rel),
        "manifest": (
            path.name in MANIFEST_NAMES
            or path.suffix.lower() == ".gemspec"
            or path.name == "jsconfig.json"
            or (path.name.startswith("tsconfig") and path.suffix.lower() == ".json")
        ),
    }
    if source:
        record.update(source_search_metadata(path))
    return record


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
    eligible = {path.relative_to(root).as_posix() for path in iter_files(root, max_files)}
    result = {
        str(path): dict(value)
        for path, value in previous.items()
        if isinstance(path, str) and isinstance(value, dict) and path in eligible
    }
    for raw in set(changed_files) | (eligible - set(result)):
        rel = Path(raw).as_posix()
        path = root / rel
        record = _file_record(root, path) if rel in eligible else None
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


def _materialize_task_view(
    root: Path,
    context_data: Dict[str, object],
    *,
    source_paths: Optional[Sequence[str]] = None,
    query: Optional[str] = None,
    targets: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, object]]:
    task = current_task(root)
    if not isinstance(task, dict):
        return None
    active_query = query if query is not None else str(task.get("request") or "")
    if source_paths is None:
        file_index = load_cache(root, "files", {})
        source_paths = [
            str(path)
            for path, item in (file_index.items() if isinstance(file_index, dict) else [])
            if isinstance(item, dict) and item.get("source")
        ]
    config = load_config(root)
    adapter = effective_adapter(root, active_query, targets)
    architecture = architecture_policy(
        root,
        config,
        source_paths=list(source_paths),
        task_request=active_query,
        target_files=targets,
    )
    json_dump(runtime_dir(root) / "active-adapter.json", adapter)
    json_dump(runtime_dir(root) / "architecture-policy.json", architecture)
    copy_to_current_task(root, "active-adapter.json", adapter)
    copy_to_current_task(root, "architecture-policy.json", architecture)
    return {
        "repository_primary": (adapter.get("stack") or {}).get("repository_primary"),
        "task_primary": (adapter.get("stack") or {}).get("task_primary"),
        "reason": (adapter.get("stack") or {}).get("task_primary_reason"),
        "scores": (adapter.get("stack") or {}).get("task_language_scores"),
        "frameworks": [
            item.get("id")
            for item in (adapter.get("frameworks") or [])
            if isinstance(item, dict)
        ],
    }


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
            task_view = _materialize_task_view(root, data)
            if task_view:
                data["task_primary_stack"] = task_view
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
            "primary": (adapter.get("primary_language") or adapter.get("language") or {}).get("id"),
            "language": (adapter.get("primary_language") or adapter.get("language") or {}).get("id"),
            "languages": [
                item.get("id") for item in (adapter.get("languages") or [])
                if isinstance(item, dict)
            ],
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
    task_view = _materialize_task_view(root, data, source_paths=source_paths)
    if task_view:
        data["task_primary_stack"] = task_view
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

            for target in targets:
                resolved = best_python_target(target, module_to_path)
                if resolved and resolved != rel:
                    edges.add((rel, resolved))
    return nodes, edges


def scan_python_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    return scan_python_dependency_sources(root, files, files)

def _jsonc(path: Path) -> Dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    pattern = re.compile(r'("(?:\\.|[^"\\])*")|(/\*.*?\*/|//[^\r\n]*)', re.S)
    stripped = pattern.sub(lambda match: match.group(1) or "", text)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _resolve_js_path(base: Path, root: Path) -> Optional[str]:
    resolved_root = root.resolve()
    candidates = []
    suffix = base.suffix.lower()
    if suffix:
        candidates.append(base)
        if suffix in {".js", ".jsx"}:
            candidates.extend([base.with_suffix(".ts"), base.with_suffix(".tsx")])
    else:
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            candidates.append(Path(str(base) + ext))
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"):
            candidates.append(base / ("index" + ext))
    for candidate in candidates:
        if not candidate.exists() or not candidate.is_file():
            continue
        try:
            return candidate.resolve().relative_to(resolved_root).as_posix()
        except ValueError:
            continue
    return None


def _js_configurations(root: Path) -> List[Dict[str, object]]:
    configs = []
    for current, dirs, files in os.walk(str(root)):
        dirs[:] = [name for name in dirs if name not in IGNORE_DIRS]
        for name in files:
            lowered = name.lower()
            if not (
                lowered == "jsconfig.json"
                or (lowered.startswith("tsconfig") and lowered.endswith(".json"))
            ):
                continue
            path = Path(current) / name
            data = _jsonc(path)
            options = data.get("compilerOptions") or {}
            if not isinstance(options, dict):
                continue
            paths = options.get("paths") or {}
            if not isinstance(paths, dict):
                paths = {}
            base_url = options.get("baseUrl")
            base = path.parent / str(base_url) if isinstance(base_url, str) else path.parent
            configs.append({
                "directory": path.parent.resolve(),
                "base_url": base.resolve(),
                "paths": {
                    str(key): [str(value) for value in values]
                    for key, values in paths.items()
                    if isinstance(key, str) and isinstance(values, list)
                },
            })
    configs.sort(key=lambda item: len(Path(item["directory"]).parts), reverse=True)
    return configs


def _workspace_patterns(data: Dict[str, object]) -> List[str]:
    workspaces = data.get("workspaces")
    if isinstance(workspaces, list):
        return [str(item) for item in workspaces if isinstance(item, str)]
    if isinstance(workspaces, dict):
        packages = workspaces.get("packages")
        if isinstance(packages, list):
            return [str(item) for item in packages if isinstance(item, str)]
    return []


def _pnpm_workspace_patterns(root: Path) -> List[str]:
    path = root / "pnpm-workspace.yaml"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []
    patterns = []
    active = False
    block_indent = 0
    for line in lines:
        stripped = line.strip()
        if not active:
            if stripped == "packages:":
                active = True
                block_indent = len(line) - len(line.lstrip())
            continue
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= block_indent and not stripped.startswith("-"):
            break
        match = re.match(r"""-\s*['"]?([^'"]+)['"]?\s*$""", stripped)
        if match:
            value = match.group(1).strip()
            if value and not value.startswith("!"):
                patterns.append(value)
    return patterns


def _workspace_packages(root: Path) -> Dict[str, Dict[str, object]]:
    root_package = _jsonc(root / "package.json")
    result = {}
    patterns = _workspace_patterns(root_package) + _pnpm_workspace_patterns(root)
    for pattern in dict.fromkeys(patterns):
        for directory in root.glob(pattern):
            package_path = directory / "package.json"
            if not package_path.is_file():
                continue
            data = _jsonc(package_path)
            name = data.get("name")
            if not isinstance(name, str) or not name:
                continue
            result[name] = {
                "directory": directory.resolve(),
                "exports": data.get("exports"),
                "source": data.get("source"),
                "module": data.get("module"),
                "main": data.get("main"),
                "types": data.get("types"),
            }
    return result


def _export_string(value: object) -> Optional[str]:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("import", "default", "require", "types", "node", "browser"):
            if key in value:
                selected = _export_string(value.get(key))
                if selected:
                    return selected
    return None


def _workspace_targets(package: Dict[str, object], subpath: str) -> List[Path]:
    directory = Path(package["directory"])
    values = []
    exports = package.get("exports")
    if not subpath:
        if isinstance(exports, dict) and "." in exports:
            selected = _export_string(exports.get("."))
            if selected:
                values.append(selected)
        else:
            selected = _export_string(exports)
            if selected:
                values.append(selected)
        for key in ("source", "module", "main", "types"):
            value = package.get(key)
            if isinstance(value, str):
                values.append(value)
        values.extend(["src/index", "index"])
    else:
        export_key = "./" + subpath
        if isinstance(exports, dict):
            selected = _export_string(exports.get(export_key))
            if selected:
                values.append(selected)
            for key, value in exports.items():
                if not isinstance(key, str) or "*" not in key:
                    continue
                prefix, _, suffix = key.partition("*")
                if export_key.startswith(prefix) and export_key.endswith(suffix):
                    wildcard = export_key[len(prefix):]
                    if suffix:
                        wildcard = wildcard[:-len(suffix)]
                    selected = _export_string(value)
                    if selected:
                        values.append(selected.replace("*", wildcard))
        values.extend([subpath, "src/" + subpath])
    return [directory / value.lstrip("./") for value in values]


def _nearest_package_root(source: Path, root: Path) -> Path:
    current = source.parent.resolve()
    resolved_root = root.resolve()
    while True:
        if (current / "package.json").is_file():
            return current
        if current == resolved_root or resolved_root not in current.parents:
            return resolved_root
        current = current.parent


def _alias_bases(
    source: Path,
    spec: str,
    root: Path,
    resolver: Dict[str, object],
) -> List[Path]:
    result = []
    source_resolved = source.resolve()
    for config in resolver.get("configs") or []:
        directory = Path(config["directory"])
        if directory != source_resolved.parent and directory not in source_resolved.parents:
            continue
        paths = config.get("paths") or {}
        for pattern, targets in paths.items():
            wildcard = None
            if "*" in pattern:
                prefix, _, suffix = pattern.partition("*")
                if not (spec.startswith(prefix) and spec.endswith(suffix)):
                    continue
                wildcard = spec[len(prefix):]
                if suffix:
                    wildcard = wildcard[:-len(suffix)]
            elif pattern != spec:
                continue
            for target in targets:
                value = target.replace("*", wildcard or "")
                result.append(Path(config["base_url"]) / value)
    if spec.startswith("@/"):
        package_root = _nearest_package_root(source, root)
        src = package_root / "src"
        if src.is_dir():
            result.append(src / spec[2:])
    return result


def _workspace_bases(spec: str, resolver: Dict[str, object]) -> List[Path]:
    packages = resolver.get("workspaces") or {}
    for name in sorted(packages, key=len, reverse=True):
        if spec == name:
            return _workspace_targets(packages[name], "")
        prefix = name + "/"
        if spec.startswith(prefix):
            return _workspace_targets(packages[name], spec[len(prefix):])
    return []


def _js_resolution_context(root: Path) -> Dict[str, object]:
    return {
        "configs": _js_configurations(root),
        "workspaces": _workspace_packages(root),
    }


def resolve_js_target(
    source: Path,
    spec: str,
    root: Path,
    resolver: Optional[Dict[str, object]] = None,
) -> Optional[str]:
    bases = []
    if spec.startswith("."):
        bases.append(source.parent / spec)
    else:
        active = resolver or _js_resolution_context(root)
        bases.extend(_alias_bases(source, spec, root, active))
        bases.extend(_workspace_bases(spec, active))
    for base in bases:
        resolved = _resolve_js_path(base.resolve(), root)
        if resolved:
            return resolved
    return None


def scan_js_dependencies(root: Path, files: Sequence[Path]) -> Tuple[Set[str], Set[Tuple[str, str]]]:
    js_ext = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
    js_files = [path for path in files if path.suffix.lower() in js_ext]
    nodes = {path.relative_to(root).as_posix() for path in js_files}
    edges = set()
    resolver = _js_resolution_context(root)
    for path in js_files:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in JS_IMPORT_RE.finditer(text):
            target = resolve_js_target(path, match.group(1), root, resolver)
            if target and target != rel:
                edges.add((rel, target))
    return nodes, edges


def strongly_connected_components(nodes: Iterable[str], edges: Iterable[Tuple[str, str]]) -> List[List[str]]:
    # Iterative Kosaraju: both passes use explicit stacks, including deep chains.
    adjacency = defaultdict(list)
    reverse = defaultdict(list)
    all_nodes = set(nodes)
    for source, target in edges:
        adjacency[source].append(target)
        reverse[target].append(source)
        all_nodes.update((source, target))
    visited = set()
    finished = []
    for node in sorted(all_nodes):
        if node in visited:
            continue
        visited.add(node)
        stack = [(node, iter(adjacency[node]))]
        while stack:
            source, children = stack[-1]
            target = next(children, None)
            if target is None:
                finished.append(source)
                stack.pop()
            elif target not in visited:
                visited.add(target)
                stack.append((target, iter(adjacency[target])))

    visited.clear()
    components = []
    for node in reversed(finished):
        if node in visited:
            continue
        visited.add(node)
        pending = [node]
        component = []
        while pending:
            source = pending.pop()
            component.append(source)
            for target in reverse[source]:
                if target not in visited:
                    visited.add(target)
                    pending.append(target)
        if len(component) > 1:
            components.append(sorted(component))
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
        scanners.append("javascript-typescript-static-imports")
    if ".php" in suffixes:
        scanners.append("php-static")
    if suffixes & {".java", ".kt", ".kts"}:
        scanners.append("java-kotlin-imports")
    if ".go" in suffixes:
        scanners.append("go-module-imports")
    if ".rs" in suffixes:
        scanners.append("rust-mod-use")
    if ".rb" in suffixes:
        scanners.append("ruby-require")

    return {
        "generated_at": utc_now(),
        "stack": stack,
        "scanners": scanners or ["project-map-only"],
        "nodes": sorted(nodes),
        "edges": [{"from": source, "to": target} for source, target in sorted(edges)],
        "dependencies": {key: sorted(values) for key, values in sorted(adjacency.items())},
        "reverse_dependencies": {key: sorted(values) for key, values in sorted(reverse.items())},
        "cycles": strongly_connected_components(nodes, edges),
        "authority": {
            "level": "advisory",
            "model": "static-best-effort",
            "note": "Use this graph to guide retrieval and impact analysis, not as proof that no runtime dependency exists.",
        },
        "limitations": [
            "Static baseline only: dynamic imports, runtime dependency injection, reflection, generated code, framework registries, macros, Rails/WordPress runtime registration, and other framework magic may require native analyzers or tests.",
            "JavaScript/TypeScript resolves relative imports, tsconfig/jsconfig path aliases, @/ source aliases, and local workspace package exports when statically discoverable; runtime/bundler-only aliases can still require native tooling.",
            "Python/JavaScript/TypeScript refresh changed files, or the affected language slice when source paths/resolution manifests change; PHP/Java/Kotlin/Go/Rust/Ruby refresh the affected language slice when those files or their module manifest change.",
        ],
        "primary_language": stack.get("primary"),
        "cache": cache_meta,
    }


def _valid_dependency_cache(data: object) -> bool:
    if not isinstance(data, dict):
        return False

    def string_list(value: object) -> bool:
        return isinstance(value, list) and all(isinstance(item, str) for item in value)

    if not string_list(data.get("nodes")):
        return False
    edges = data.get("edges")
    if not isinstance(edges, list) or not all(
        isinstance(item, dict)
        and isinstance(item.get("from"), str)
        and isinstance(item.get("to"), str)
        for item in edges
    ):
        return False
    for key in ("dependencies", "reverse_dependencies"):
        mapping = data.get(key)
        if not isinstance(mapping, dict) or not all(
            isinstance(path, str) and string_list(targets)
            for path, targets in mapping.items()
        ):
            return False
    cycles = data.get("cycles")
    return isinstance(cycles, list) and all(string_list(cycle) for cycle in cycles)


def dependency_graph(root: Path, force: bool = False) -> Dict[str, object]:
    context = project_context(root, force=force)
    force = force or context["cache"]["mode"] == "FULL_REBUILD"
    refresh = cache_status(root, "dependency", force=force)
    previous = None
    if refresh["mode"] != "FULL_REBUILD":
        previous = load_cache(root, "dependency")
    if refresh["mode"] != "FULL_REBUILD" and not _valid_dependency_cache(previous):
        refresh = {
            "mode": "FULL_REBUILD",
            "reason": "dependency-cache-invalid",
            "changed_files": [],
            "repo_state": refresh["repo_state"],
        }
    if refresh["mode"] == "CACHE_HIT":
        data = dict(previous)
        data["cache"] = {
            "mode": "CACHE_HIT",
            "reason": refresh["reason"],
            "changed_files": [],
        }
        json_dump(runtime_dir(root) / "dependency-map.json", data)
        return data

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
        nodes = set(str(item) for item in (previous.get("nodes") or []))
        edges = edge_set(previous)
        changed = {Path(item).as_posix() for item in refresh["changed_files"]}
        current_sources = set(source_paths)
        deleted = nodes - current_sources
        changed_current = {path for path in changed if path in current_sources}
        rescan_sources = set(changed_current)
        js_ext = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}
        # A new/deleted module can change imports in files whose contents did not
        # change. Re-resolve that language slice when its path universe changes.
        for extensions in ({".py"}, js_ext):
            old_paths = {path for path in nodes if Path(path).suffix.lower() in extensions}
            new_paths = {path for path in current_sources if Path(path).suffix.lower() in extensions}
            if old_paths != new_paths:
                rescan_sources.update(new_paths)

        js_resolution_manifest_changed = any(
            Path(path).name in {"package.json", "pnpm-workspace.yaml"}
            or Path(path).name == "jsconfig.json"
            or (Path(path).name.startswith("tsconfig") and Path(path).suffix.lower() == ".json")
            for path in changed
        )
        if js_resolution_manifest_changed:
            rescan_sources.update(
                path for path in current_sources if Path(path).suffix.lower() in js_ext
            )

        edges = {
            (source, target) for source, target in edges
            if source not in rescan_sources
            and source not in deleted
            and target not in deleted
        }
        nodes.difference_update(deleted)
        nodes.update(changed_current)

        python_changed = [
            root / path for path in sorted(rescan_sources) if Path(path).suffix.lower() == ".py"
        ]
        if python_changed:
            py_nodes, py_edges = scan_python_dependency_sources(
                root,
                python_changed,
                [root / path for path in source_paths if Path(path).suffix.lower() == ".py"],
            )
            nodes.update(py_nodes)
            edges.update(py_edges)

        js_changed = [
            root / path for path in sorted(rescan_sources) if Path(path).suffix.lower() in js_ext
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
            ({".rb"}, {"Gemfile", "Gemfile.lock", "Rakefile"}),
        ]
        for extensions, manifests in language_groups:
            needs_refresh = any(Path(path).suffix.lower() in extensions for path in changed)
            needs_refresh = needs_refresh or any(Path(path).name in manifests for path in changed)
            if ".rb" in extensions:
                needs_refresh = needs_refresh or any(Path(path).suffix.lower() == ".gemspec" for path in changed)
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
        nodes.update(source_paths)
        cache_meta = {
            "mode": "FULL_REBUILD",
            "reason": refresh["reason"],
            "changed_files": list(refresh["changed_files"]),
        }

    # Resolvers must not reintroduce Git-ignored or otherwise excluded targets.
    nodes = set(source_paths)
    edges = {(source, target) for source, target in edges if source in nodes and target in nodes}
    data = _dependency_payload(root, nodes, edges, stack, cache_meta)
    json_dump(runtime_dir(root) / "dependency-map.json", data)
    write_cache(root, "dependency", data, refresh["repo_state"])
    return data

def changed_files(root: Path) -> List[str]:
    output = []
    for record in current_repo_state(root).get("dirty", []):
        output.append(record["path"])
        if record["old_path"]:
            output.append(record["old_path"])
    return sorted(set(output))


def relevant_context(
    root: Path,
    targets: Optional[Sequence[str]] = None,
    query: Optional[str] = None,
) -> Dict[str, object]:
    context = project_context(root)
    graph = dependency_graph(root)
    config = load_config(root)
    context_config = config.get("context") or {}
    retrieval_config = context_config.get("retrieval") or {}
    depth = int(context_config.get("max_dependency_depth", 2))
    max_source = int(context_config.get("max_source_files", 20))
    max_tests = int(context_config.get("max_test_files", 10))
    max_modules = int(context_config.get("max_related_modules", 8))

    active_query = query or ""
    task = current_task(root)
    if not active_query and isinstance(task, dict):
        active_query = str(task.get("request") or "")

    file_index = load_cache(root, "files", {})
    if not isinstance(file_index, dict):
        file_index = {}

    data = build_relevant_payload(
        root,
        graph=graph,
        context=context,
        file_index=file_index,
        query=active_query,
        targets=targets,
        changed_files=changed_files(root),
        depth=depth,
        max_source=max_source,
        max_tests=max_tests,
        max_modules=max_modules,
        min_index_score=int(retrieval_config.get("min_index_score", 6)),
        fallback_max_scan_files=int(retrieval_config.get("fallback_max_scan_files", 20000)),
        fallback_read_bytes=int(retrieval_config.get("fallback_read_bytes", 131072)),
        custom_aliases=(
            retrieval_config.get("query_aliases")
            if isinstance(retrieval_config.get("query_aliases"), dict)
            else {}
        ),
    )
    data["generated_at"] = utc_now()
    data["history_policy"] = {
        "auto_load_history": bool((config.get("tasks") or {}).get("auto_load_history", False)),
        "retention": (config.get("tasks") or {}).get("retention"),
        "note": "Historical task folders are cold storage and are not loaded automatically.",
    }

    source_paths = [
        str(path)
        for path, item in file_index.items()
        if isinstance(item, dict) and item.get("source")
    ]
    task_view = _materialize_task_view(
        root,
        context,
        source_paths=source_paths,
        query=active_query,
        targets=data.get("targets") or [],
    )
    if task_view:
        data["task_primary_stack"] = task_view

    json_dump(runtime_dir(root) / "relevant-context.json", data)
    copy_to_current_task(root, "relevant-context.json", data)
    return data


def impact_analysis(root: Path, targets: Optional[Sequence[str]] = None) -> Dict[str, object]:
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
        "dependency_authority": graph.get("authority"),
        "depth": depth,
    }
    json_dump(runtime_dir(root) / "impact.json", data)
    copy_to_current_task(root, "impact.json", data)
    return data


def _dependency_baseline(task_path: Path) -> Dict[str, object]:
    before = json_load(task_path / "dependency-before.json", None)
    if not _valid_dependency_cache(before):
        raise RuntimeError(
            "Dependency baseline is missing or invalid. Preserve existing evidence; "
            "do not create a replacement baseline after implementation has started."
        )
    return before


def snapshot_dependencies(root: Path, when: str) -> Dict[str, object]:
    if when not in {"before", "after"}:
        raise ValueError("Snapshot must be before or after")
    task_path = current_task_path(root)
    if not task_path:
        raise RuntimeError("No current task. Start one before taking a snapshot.")
    if when == "before" and (task_path / "dependency-before.json").exists():
        return _dependency_baseline(task_path)
    if when == "after":
        _dependency_baseline(task_path)
    graph = dependency_graph(root)
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
    before = _dependency_baseline(task_path)
    after = json_load(task_path / "dependency-after.json", None)
    if not _valid_dependency_cache(after):
        raise RuntimeError("Dependency after snapshot is missing or invalid. Refresh it before comparing.")

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


def verification_fingerprint(root: Path) -> str:
    """Bind evidence to file contents while reusing persistent hashes for unchanged files."""
    config = load_config(root)
    relative_files = [
        path.relative_to(root).as_posix()
        for path in iter_files(root, max_files=int(config["context"].get("max_files", 20000)))
    ]
    control = config_path(root)
    extra_files = [control.relative_to(root).as_posix()] if control.is_file() else []
    hashes = content_hash_index(root, relative_files, extra_files=extra_files)
    digest = hashlib.sha256()
    for relative, content_hash in sorted(hashes.items()):
        digest.update(relative.encode("utf-8") + b"\0")
        try:
            digest.update(bytes.fromhex(content_hash))
        except ValueError as exc:
            raise RuntimeError("Invalid cached verification hash: {}".format(relative)) from exc
    return digest.hexdigest()


def verify(root: Path) -> Dict[str, object]:
    task_path = current_task_path(root)
    dep_diff = None
    if task_path and (task_path / "dependency-before.json").exists():
        _dependency_baseline(task_path)

    config = load_config(root)
    verification = config.get("verification") or {}
    commands = verification.get("commands") or []
    require_commands = bool(verification.get("require_commands", True))
    results = []
    initial_fingerprint = verification_fingerprint(root)
    last_fingerprint = initial_fingerprint
    inputs_changed = False

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
        result = run_process(command, cwd=root)
        final_fingerprint = verification_fingerprint(root)
        result["input_fingerprint_before"] = last_fingerprint
        result["input_fingerprint_after"] = final_fingerprint
        inputs_changed = inputs_changed or final_fingerprint != last_fingerprint
        last_fingerprint = final_fingerprint
        results.append(result)

    # Commands may format or generate source; compare dependencies of the final tree.
    if task_path and (task_path / "dependency-before.json").exists():
        final_graph = snapshot_dependencies(root, "after")
        dep_diff = dependency_diff(root)
    else:
        final_graph = dependency_graph(root)
    final_fingerprint = verification_fingerprint(root)
    inputs_changed = inputs_changed or final_fingerprint != last_fingerprint

    failed_commands = [item for item in results if item.get("returncode") != 0]
    fail_on_new_cycles = bool((config.get("dependency") or {}).get("fail_on_new_cycles", True))
    new_cycles = []
    if isinstance(dep_diff, dict):
        new_cycles = dep_diff.get("new_cycles") or []

    if not commands:
        status = "NEEDS_VERIFICATION_CONFIG"
    elif failed_commands or inputs_changed or (fail_on_new_cycles and new_cycles):
        status = "FAIL_VERIFICATION"
    else:
        status = "PASS_VERIFIED"

    architecture = json_load(runtime_dir(root) / "architecture-policy.json", {})
    data = {
        "generated_at": utc_now(),
        "status": status,
        "task_id": (current_task(root) or {}).get("id"),
        "source_fingerprint": final_fingerprint,
        "input_fingerprint_before": initial_fingerprint,
        "inputs_changed_during_verification": inputs_changed,
        "rerun_required": inputs_changed,
        "rerun_commands": commands if inputs_changed else [],
        "rerun_reason": "Verification inputs changed; rerun all configured commands against the final tree." if inputs_changed else None,
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
        "dependency_authority": final_graph.get("authority") if isinstance(final_graph, dict) else None,
        "new_cycles": new_cycles,
        "git_status": (git(root, "status", "--short") or "").splitlines(),
        "git_diff_stat": git(root, "diff", "--stat"),
    }
    json_dump(runtime_dir(root) / "verification.json", data)
    copy_to_current_task(root, "verification.json", data)
    return data


def status(root: Path) -> Dict[str, object]:
    task = current_task(root)
    report = json_load(runtime_dir(root) / "verification.json")
    verification_current = (
        isinstance(report, dict)
        and report.get("task_id") == (task or {}).get("id")
        and report.get("source_fingerprint") == verification_fingerprint(root)
    )
    return {
        "root": str(root),
        "task": task,
        "verification_current": verification_current,
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
