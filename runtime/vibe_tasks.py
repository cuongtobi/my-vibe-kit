"""Task records and explicit lifecycle management for my-vibe-kit."""

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from vibe_contracts import ContractError, artifact_is_valid, stamp_artifact


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


def tasks_dir(root: Path) -> Path:
    return root / ".vibe" / "tasks"


def runtime_dir(root: Path) -> Path:
    return root / ".vibe" / "runtime"


def slugify(value: str, limit: int = 48) -> str:
    import re

    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip()).strip("-").lower()
    return (slug or "task")[:limit].rstrip("-")


def _safe_task_path(root: Path, value: object) -> Optional[Path]:
    if not isinstance(value, str) or not value:
        return None
    base = tasks_dir(root).resolve()
    candidate = (root / value).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate


def start_task(root: Path, mode: str, request: str) -> Dict[str, object]:
    valid_modes = {"feature", "change", "bug_fix", "refactor", "hotfix"}
    if mode not in valid_modes:
        raise ValueError("Unsupported mode: {}".format(mode))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    while True:
        task_id = "{}-{}-{}-{}".format(
            stamp,
            mode.replace("_", "-"),
            slugify(request),
            uuid.uuid4().hex[:12],
        )
        task_path = tasks_dir(root) / task_id
        try:
            task_path.mkdir(parents=True, exist_ok=False)
            break
        except FileExistsError:
            continue

    task = stamp_artifact("task", {
        "id": task_id,
        "mode": mode,
        "request": request,
        "created_at": utc_now(),
        "path": str(task_path.relative_to(root)),
    })
    json_dump(task_path / "task.json", task)
    (task_path / "request.md").write_text(request.strip() + "\n", encoding="utf-8")
    json_dump(runtime_dir(root) / "current-task.json", task)
    return task


def current_task(root: Path) -> Optional[Dict[str, object]]:
    path = runtime_dir(root) / "current-task.json"
    data = json_load(path, None)
    if artifact_is_valid("task", data):
        return data if _safe_task_path(root, data.get("path")) is not None else None
    if not isinstance(data, dict):
        return None
    # Pre-contract task records are safe to migrate only when they have no
    # version/type markers and still satisfy the current task shape.
    if "artifact_type" in data or "schema_version" in data:
        return None
    required = ("id", "mode", "request", "created_at", "path")
    if not all(isinstance(data.get(key), str) and str(data.get(key)).strip() for key in required):
        return None
    if data.get("mode") not in {"feature", "change", "bug_fix", "refactor", "hotfix"}:
        return None
    try:
        migrated = stamp_artifact("task", data)
    except ContractError:
        return None
    task_path = _safe_task_path(root, migrated.get("path"))
    if task_path is None:
        return None
    json_dump(path, migrated)
    if task_path.is_dir():
        json_dump(task_path / "task.json", migrated)
    return migrated


def current_task_path(root: Path) -> Optional[Path]:
    task = current_task(root)
    if not task:
        return None
    return _safe_task_path(root, task.get("path"))


def copy_to_current_task(root: Path, filename: str, data: object) -> None:
    path = current_task_path(root)
    if path:
        json_dump(path / filename, data)


def _parse_created_at(value: object) -> Optional[datetime]:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def task_records(root: Path) -> List[Dict[str, object]]:
    current_id = (current_task(root) or {}).get("id")
    records: List[Dict[str, object]] = []
    base = tasks_dir(root)
    if not base.exists():
        return records

    for path in sorted(base.iterdir()):
        if not path.is_dir():
            continue
        data = json_load(path / "task.json", {})
        if not isinstance(data, dict):
            data = {}
        created_at = _parse_created_at(data.get("created_at"))
        records.append(
            {
                "id": str(data.get("id") or path.name),
                "path": str(path.relative_to(root)),
                "created_at": created_at.isoformat() if created_at else None,
                "created_at_dt": created_at,
                "current": str(data.get("id") or path.name) == current_id,
                "mode": data.get("mode"),
                "request": data.get("request"),
            }
        )
    records.sort(
        key=lambda item: item.get("created_at_dt") or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return records


def task_lifecycle(
    root: Path,
    config: Dict[str, object],
    *,
    apply: bool = False,
) -> Dict[str, object]:
    tasks_config = config.get("tasks") if isinstance(config, dict) else {}
    tasks_config = tasks_config if isinstance(tasks_config, dict) else {}
    retention = tasks_config.get("retention")
    retention = retention if isinstance(retention, dict) else {}

    policy = str(retention.get("policy", "bounded"))
    max_tasks = int(retention.get("max_tasks", 100))
    max_age_days = int(retention.get("max_age_days", 90))
    cleanup = str(retention.get("cleanup", "manual"))
    if policy not in {"bounded", "keep-all"}:
        policy = "bounded"
    if cleanup != "manual":
        cleanup = "manual"

    records = task_records(root)
    now = datetime.now(timezone.utc)
    candidates: Dict[str, Dict[str, object]] = {}

    if policy == "bounded":
        non_current = [item for item in records if not item["current"]]
        for item in non_current:
            created = item.get("created_at_dt")
            if isinstance(created, datetime):
                age_days = (now - created).total_seconds() / 86400
                if age_days > max_age_days:
                    candidate = dict(item)
                    candidate["reason"] = "age"
                    candidate["age_days"] = round(age_days, 1)
                    candidates[str(item["id"])] = candidate

        if max_tasks >= 0 and len(records) > max_tasks:
            keep_ids = {
                str(item["id"])
                for item in records[:max_tasks]
            }
            for item in non_current:
                if str(item["id"]) not in keep_ids:
                    candidate = candidates.get(str(item["id"]), dict(item))
                    candidate["reason"] = (
                        "age+count" if candidate.get("reason") == "age" else "count"
                    )
                    candidates[str(item["id"])] = candidate

    deleted: List[str] = []
    if apply:
        for task_id, item in sorted(candidates.items()):
            path = root / str(item["path"])
            if path.is_dir():
                shutil.rmtree(path)
                deleted.append(task_id)

    def public(item: Dict[str, object]) -> Dict[str, object]:
        return {
            key: value
            for key, value in item.items()
            if key != "created_at_dt"
        }

    return {
        "policy": policy,
        "cleanup": cleanup,
        "max_tasks": max_tasks,
        "max_age_days": max_age_days,
        "task_count": len(records),
        "current_task_id": (current_task(root) or {}).get("id"),
        "candidates": [public(item) for item in candidates.values()],
        "candidate_count": len(candidates),
        "apply": apply,
        "deleted": deleted,
        "deleted_count": len(deleted),
        "note": (
            "Cleanup is explicit. Run task gc --apply to delete only non-current candidates."
            if cleanup == "manual"
            else ""
        ),
    }
