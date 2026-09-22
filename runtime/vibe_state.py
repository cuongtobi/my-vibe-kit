"""Persistent repository-state cache and Git-aware incremental refresh helpers."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

STATE_SCHEMA_VERSION = 1
SCANNER_VERSION = "incremental-v1"

CACHE_FILES = {
    "context": "last-context.json",
    "dependency": "last-dependency.json",
    "framework": "last-framework.json",
    "adapter": "last-adapter.json",
    "architecture": "last-architecture.json",
    "files": "file-index.json",
}

IGNORED_STATE_PREFIXES = (
    ".vibe/runtime/",
    ".vibe/state/",
    ".vibe/tasks/",
    ".vibe/tools/",
    ".vibe/adapters/",
    ".agents/",
    ".claude/",
)
IGNORED_STATE_EXACT = {".vibe/.gitignore"}


def state_dir(root: Path) -> Path:
    return root / ".vibe" / "state"


def _json_load(path: Path, default: object = None) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _json_dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _git(root: Path, *args: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git"] + list(args),
            cwd=str(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _normalized(path: str) -> str:
    return Path(path.strip().strip('"')).as_posix()


def _ignored_state_path(path: str) -> bool:
    value = _normalized(path)
    if value in IGNORED_STATE_EXACT:
        return True
    return any(value.startswith(prefix) for prefix in IGNORED_STATE_PREFIXES)


def _parse_status_line(line: str) -> Optional[Dict[str, str]]:
    if len(line) < 4:
        return None
    status = line[:2]
    raw = line[3:]
    old_path = ""
    path = raw
    if " -> " in raw:
        old_path, path = raw.split(" -> ", 1)
    path = _normalized(path)
    old_path = _normalized(old_path) if old_path else ""
    if _ignored_state_path(path) and (not old_path or _ignored_state_path(old_path)):
        return None
    return {"status": status, "path": path, "old_path": old_path}


def _file_sha256(root: Path, relative: str) -> Optional[str]:
    path = root / relative
    if not path.exists() or not path.is_file() or path.is_symlink():
        return None
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def current_repo_state(root: Path) -> Dict[str, object]:
    head = _git(root, "rev-parse", "HEAD")
    status_text = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    if head is None and status_text is None:
        return {
            "git": False,
            "head": None,
            "dirty": [],
            "fingerprint": None,
        }

    dirty = []
    for line in (status_text or "").splitlines():
        parsed = _parse_status_line(line)
        if not parsed:
            continue
        parsed["sha256"] = _file_sha256(root, parsed["path"])
        dirty.append(parsed)
    dirty.sort(key=lambda item: (item["path"], item["old_path"], item["status"]))

    payload = {
        "head": head,
        "dirty": dirty,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "git": True,
        "head": head,
        "dirty": dirty,
        "fingerprint": fingerprint,
    }


def load_index_state(root: Path) -> Dict[str, object]:
    data = _json_load(state_dir(root) / "index-state.json", {})
    if not isinstance(data, dict):
        data = {}
    if data.get("schema_version") != STATE_SCHEMA_VERSION:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "scanner_version": SCANNER_VERSION,
            "artifacts": {},
        }
    if data.get("scanner_version") != SCANNER_VERSION:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "scanner_version": SCANNER_VERSION,
            "artifacts": {},
        }
    data.setdefault("artifacts", {})
    return data


def save_index_state(root: Path, data: Dict[str, object]) -> None:
    data["schema_version"] = STATE_SCHEMA_VERSION
    data["scanner_version"] = SCANNER_VERSION
    data.setdefault("artifacts", {})
    _json_dump(state_dir(root) / "index-state.json", data)


def cache_path(root: Path, artifact: str) -> Path:
    name = CACHE_FILES.get(artifact)
    if not name:
        raise ValueError("Unknown cache artifact: {}".format(artifact))
    return state_dir(root) / name


def load_cache(root: Path, artifact: str, default: object = None) -> object:
    return _json_load(cache_path(root, artifact), default)


def write_cache(
    root: Path,
    artifact: str,
    data: object,
    repo_state: Optional[Dict[str, object]] = None,
) -> None:
    state = repo_state or current_repo_state(root)
    _json_dump(cache_path(root, artifact), data)
    index = load_index_state(root)
    artifacts = index.setdefault("artifacts", {})
    artifacts[artifact] = {
        "fingerprint": state.get("fingerprint"),
        "repo_state": state,
    }
    save_index_state(root, index)


def _parse_name_status(text: str) -> Set[str]:
    paths: Set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        code = parts[0]
        if code.startswith(("R", "C")) and len(parts) >= 3:
            for raw in parts[1:3]:
                value = _normalized(raw)
                if not _ignored_state_path(value):
                    paths.add(value)
        elif len(parts) >= 2:
            value = _normalized(parts[-1])
            if not _ignored_state_path(value):
                paths.add(value)
    return paths


def _dirty_map(repo_state: Dict[str, object]) -> Dict[str, Tuple[str, Optional[str], str]]:
    out = {}
    for item in repo_state.get("dirty") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        if not path:
            continue
        out[path] = (
            str(item.get("status") or ""),
            item.get("sha256"),
            str(item.get("old_path") or ""),
        )
    return out


def changed_paths_between(
    root: Path,
    previous: Dict[str, object],
    current: Dict[str, object],
) -> Optional[List[str]]:
    if not previous.get("git") or not current.get("git"):
        return None

    changed: Set[str] = set()
    previous_head = previous.get("head")
    current_head = current.get("head")
    if previous_head != current_head:
        if not previous_head or not current_head:
            return None
        diff = _git(
            root,
            "diff",
            "--name-status",
            "--find-renames",
            str(previous_head) + ".." + str(current_head),
        )
        if diff is None:
            return None
        changed.update(_parse_name_status(diff))

    before_dirty = _dirty_map(previous)
    after_dirty = _dirty_map(current)
    for path in set(before_dirty) | set(after_dirty):
        if before_dirty.get(path) != after_dirty.get(path):
            if not _ignored_state_path(path):
                changed.add(path)
            before = before_dirty.get(path)
            after = after_dirty.get(path)
            for record in (before, after):
                if record and record[2] and not _ignored_state_path(record[2]):
                    changed.add(record[2])

    return sorted(changed)


def cache_status(
    root: Path,
    artifact: str,
    *,
    force: bool = False,
) -> Dict[str, object]:
    current = current_repo_state(root)
    if force:
        return {
            "mode": "FULL_REBUILD",
            "reason": "forced",
            "changed_files": [],
            "repo_state": current,
        }

    path = cache_path(root, artifact)
    index = load_index_state(root)
    meta = (index.get("artifacts") or {}).get(artifact)
    if not path.exists() or not isinstance(meta, dict):
        return {
            "mode": "FULL_REBUILD",
            "reason": "cache-missing",
            "changed_files": [],
            "repo_state": current,
        }

    if meta.get("fingerprint") == current.get("fingerprint") and current.get("fingerprint"):
        return {
            "mode": "CACHE_HIT",
            "reason": "repository-state-unchanged",
            "changed_files": [],
            "repo_state": current,
        }

    previous = meta.get("repo_state")
    if not isinstance(previous, dict):
        return {
            "mode": "FULL_REBUILD",
            "reason": "previous-repository-state-missing",
            "changed_files": [],
            "repo_state": current,
        }

    delta = changed_paths_between(root, previous, current)
    if delta is None:
        return {
            "mode": "FULL_REBUILD",
            "reason": "git-delta-unavailable",
            "changed_files": [],
            "repo_state": current,
        }
    return {
        "mode": "INCREMENTAL_REFRESH",
        "reason": "repository-delta-detected",
        "changed_files": delta,
        "repo_state": current,
    }


def state_summary(root: Path) -> Dict[str, object]:
    index = load_index_state(root)
    current = current_repo_state(root)
    artifacts = {}
    for artifact in ("context", "dependency"):
        status = cache_status(root, artifact)
        artifacts[artifact] = {
            "mode": status["mode"],
            "reason": status["reason"],
            "changed_files": status["changed_files"],
        }
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "scanner_version": SCANNER_VERSION,
        "current_repository_state": current,
        "artifacts": artifacts,
        "cached_artifacts": sorted((index.get("artifacts") or {}).keys()),
    }
