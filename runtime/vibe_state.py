"""Persistent repository-state cache and Git-aware incremental refresh helpers."""

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

STATE_SCHEMA_VERSION = 1
SCANNER_VERSION = "incremental-v6"

CACHE_FILES = {
    "context": "last-context.json",
    "dependency": "last-dependency.json",
    "framework": "last-framework.json",
    "adapter": "last-adapter.json",
    "architecture": "last-architecture.json",
    "files": "file-index.json",
    "hashes": "content-hashes.json",
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
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
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
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    output = proc.stdout.decode("utf-8", errors="replace")
    return output if "-z" in args else output.rstrip("\r\n")


def _normalized(path: str) -> str:
    # Git -z paths are literal, including leading/trailing whitespace and quotes.
    return Path(path).as_posix() if path else ""


def _ignored_state_path(path: str) -> bool:
    value = _normalized(path)
    if value in IGNORED_STATE_EXACT:
        return True
    return any(value.startswith(prefix) for prefix in IGNORED_STATE_PREFIXES)


def _parse_status(text: str) -> List[Dict[str, str]]:
    records = iter(text.split("\0"))
    result = []
    for record in records:
        if len(record) < 4:
            continue
        status, path = record[:2], _normalized(record[3:])
        # Porcelain v1 -z emits the destination before the rename/copy source.
        old_path = _normalized(next(records, "")) if "R" in status or "C" in status else ""
        if _ignored_state_path(path) and (not old_path or _ignored_state_path(old_path)):
            continue
        result.append({"status": status, "path": path, "old_path": old_path})
    return result


def repository_files(root: Path) -> Optional[List[str]]:
    """Tracked files plus non-ignored untracked files; None outside Git."""
    output = _git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if output is None:
        return None
    return sorted({_normalized(path) for path in output.split("\0") if path})


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
    status_text = _git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if head is None and status_text is None:
        return {
            "git": False,
            "head": None,
            "dirty": [],
            "fingerprint": None,
        }

    dirty = []
    for parsed in _parse_status(status_text or ""):
        parsed["sha256"] = _file_sha256(root, parsed["path"])
        dirty.append(parsed)
    dirty.sort(key=lambda item: (item["path"], item["old_path"], item["status"]))

    payload = {
        "head": head,
        "dirty": dirty,
        "config_sha256": _file_sha256(root, ".vibe/config.json"),
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "git": True,
        "head": head,
        "dirty": dirty,
        "config_sha256": payload["config_sha256"],
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
    if not isinstance(data.get("artifacts"), dict):
        data["artifacts"] = {}
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
        "sha256": _file_sha256(root, cache_path(root, artifact).relative_to(root).as_posix()),
    }
    save_index_state(root, index)


def _parse_name_status(text: str) -> Set[str]:
    paths: Set[str] = set()
    records = iter(text.split("\0"))
    for code in records:
        if not code:
            continue
        for _ in range(2 if code.startswith(("R", "C")) else 1):
            value = _normalized(next(records, ""))
            if value and value != "." and not _ignored_state_path(value):
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
    if previous.get("config_sha256") != current.get("config_sha256"):
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
            "-z",
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

    # Checksums cover all persisted bytes, including valid-but-incomplete JSON.
    # Context and its supporting artifacts must also come from the same state.
    required = [artifact]
    if artifact in {"context", "dependency"}:
        required += ["context", "files", "framework", "adapter", "architecture"]
    artifacts = index["artifacts"]
    context_meta = artifacts.get("context") or {}
    context_bundle = {"context", "files", "framework", "adapter", "architecture"}
    for name in set(required):
        item = artifacts.get(name)
        digest = _file_sha256(root, cache_path(root, name).relative_to(root).as_posix())
        if (
            not isinstance(item, dict)
            or not digest or item.get("sha256") != digest
            or load_cache(root, name) is None
            or (name in context_bundle and isinstance(context_meta, dict)
                and item.get("fingerprint") != context_meta.get("fingerprint"))
        ):
            return {
                "mode": "FULL_REBUILD", "reason": "cache-bundle-invalid",
                "changed_files": [], "repo_state": current,
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

    config = _json_load(root / ".vibe" / "config.json", {})
    index_config = config.get("index", {}) if isinstance(config, dict) else {}
    if isinstance(index_config, dict) and index_config.get("use_git_delta") is False:
        return {
            "mode": "FULL_REBUILD", "reason": "git-delta-disabled",
            "changed_files": [], "repo_state": current,
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



def content_hash_index(
    root: Path,
    files: Sequence[str],
    *,
    extra_files: Sequence[str] = (),
    force: bool = False,
) -> Dict[str, str]:
    """Reuse persisted content hashes and re-hash only repository deltas when possible."""
    universe = sorted({
        _normalized(path)
        for path in list(files) + list(extra_files)
        if path and not _ignored_state_path(_normalized(path))
    })
    refresh = cache_status(root, "hashes", force=force)
    previous = load_cache(root, "hashes", {})
    if not isinstance(previous, dict) or not all(
        isinstance(path, str) and isinstance(value, str)
        for path, value in previous.items()
    ):
        previous = {}
        refresh = {
            "mode": "FULL_REBUILD",
            "reason": "hash-cache-invalid",
            "changed_files": [],
            "repo_state": current_repo_state(root),
        }

    if refresh["mode"] == "CACHE_HIT":
        hashes = {path: previous[path] for path in universe if path in previous}
        missing = [path for path in universe if path not in hashes]
        if not missing:
            return hashes
    elif refresh["mode"] == "INCREMENTAL_REFRESH":
        hashes = {path: previous[path] for path in universe if path in previous}
        missing = [
            path for path in universe
            if path not in hashes or path in set(refresh["changed_files"])
        ]
    else:
        hashes = {}
        missing = universe

    for relative in missing:
        digest = _file_sha256(root, relative)
        if digest:
            hashes[relative] = digest
        else:
            hashes.pop(relative, None)

    hashes = {path: hashes[path] for path in universe if path in hashes}
    write_cache(root, "hashes", hashes, refresh["repo_state"])
    return hashes

def state_summary(root: Path) -> Dict[str, object]:
    index = load_index_state(root)
    current = current_repo_state(root)
    artifacts = {}
    for artifact in ("context", "dependency", "hashes"):
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
