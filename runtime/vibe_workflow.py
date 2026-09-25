"""Structured task evidence and deterministic workflow completion gate."""

import json
from pathlib import Path
from typing import Dict, Optional

from vibe_contracts import (
    ContractError,
    stamp_artifact,
    validate_acceptance_semantics,
    validate_artifact,
    validate_security_semantics,
)
from vibe_tasks import current_task, current_task_path


EVIDENCE_FILES = {
    "acceptance": ("acceptance-evidence", "acceptance-evidence.json"),
    "security": ("security-evidence", "security-evidence.json"),
}


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def record_evidence(root: Path, kind: str, payload: object) -> Dict[str, object]:
    if kind not in EVIDENCE_FILES:
        raise ContractError("Unsupported evidence kind: {}".format(kind))
    task = current_task(root)
    task_path = current_task_path(root)
    if not isinstance(task, dict) or task_path is None:
        raise ContractError("No current task. Start a task before recording evidence.")
    if not isinstance(payload, dict):
        raise ContractError("Evidence payload must be a JSON object.")

    artifact_kind, filename = EVIDENCE_FILES[kind]
    verification_path = root / ".vibe" / "runtime" / "verification.json"
    verification = _read_json(verification_path)
    try:
        verification = validate_artifact("verification", verification)
    except ContractError as exc:
        raise ContractError("Current valid verification evidence is required before recording task evidence.") from exc
    if verification.get("task_id") != task.get("id"):
        raise ContractError("Verification evidence does not belong to the current task.")

    data = dict(payload)
    supplied_task = data.get("task_id")
    if supplied_task not in (None, task.get("id")):
        raise ContractError("Evidence task_id does not match the current task.")
    data["task_id"] = task.get("id")
    data["source_fingerprint"] = verification.get("source_fingerprint")
    data = stamp_artifact(artifact_kind, data)
    if kind == "acceptance":
        validate_acceptance_semantics(data)
    else:
        validate_security_semantics(data)

    _write_json(task_path / filename, data)
    _write_json(root / ".vibe" / "runtime" / filename, data)
    return data


def load_evidence(root: Path, kind: str) -> Optional[Dict[str, object]]:
    if kind not in EVIDENCE_FILES:
        raise ContractError("Unsupported evidence kind: {}".format(kind))
    task_path = current_task_path(root)
    if task_path is None:
        return None
    artifact_kind, filename = EVIDENCE_FILES[kind]
    data = _read_json(task_path / filename)
    try:
        value = validate_artifact(artifact_kind, data)
        if kind == "acceptance":
            validate_acceptance_semantics(value)
        else:
            validate_security_semantics(value)
        return value
    except ContractError:
        return None


def evaluate_completion(
    root: Path,
    *,
    verification: object,
    verification_current: bool,
    security_candidates: object = None,
) -> Dict[str, object]:
    task = current_task(root)
    reasons = []
    verification_ok = False
    task_id = task.get("id") if isinstance(task, dict) else None

    try:
        report = validate_artifact("verification", verification)
        verification_ok = (
            report.get("status") == "PASS_VERIFIED"
            and report.get("task_id") == task_id
            and verification_current
        )
    except ContractError:
        report = None
    if not verification_ok:
        reasons.append("runtime-verification-not-current-pass")

    acceptance = load_evidence(root, "acceptance")
    acceptance_ok = False
    report_fingerprint = report.get("source_fingerprint") if isinstance(report, dict) else None
    if (
        isinstance(acceptance, dict)
        and acceptance.get("task_id") == task_id
        and acceptance.get("source_fingerprint") == report_fingerprint
    ):
        criteria = acceptance.get("criteria") or []
        acceptance_ok = bool(criteria) and all(
            isinstance(item, dict) and item.get("result") == "met" for item in criteria
        )
    if not acceptance_ok:
        reasons.append("acceptance-evidence-incomplete")

    candidates = []
    try:
        candidate_report = validate_artifact("security-candidates", security_candidates)
        candidates = list(candidate_report.get("surfaces") or [])
    except ContractError:
        candidate_report = None

    security = load_evidence(root, "security")
    security_ok = False
    if (
        isinstance(security, dict)
        and security.get("task_id") == task_id
        and security.get("source_fingerprint") == report_fingerprint
    ):
        classification = security.get("classification")
        if classification == "not-security-sensitive":
            override = str(security.get("candidate_override_reason") or "").strip()
            security_ok = not candidates or bool(override)
        elif classification == "security-sensitive":
            surfaces = security.get("surfaces") or []
            trust = security.get("trust_boundaries") or []
            abuse_cases = security.get("abuse_cases") or []
            controls = security.get("controls_reviewed") or []
            checks = security.get("targeted_checks") or []
            diff_review = security.get("diff_review") or {}
            diff_evidence = diff_review.get("evidence")
            if isinstance(diff_evidence, str):
                diff_evidence_ok = bool(diff_evidence.strip())
            elif isinstance(diff_evidence, list):
                diff_evidence_ok = bool(diff_evidence) and all(
                    isinstance(value, str) and value.strip() for value in diff_evidence
                )
            else:
                diff_evidence_ok = False
            scanner = security.get("scanner") or {}
            dependency = security.get("dependency_vulnerability") or {}
            security_ok = (
                bool(surfaces)
                and bool(trust)
                and bool(abuse_cases)
                and bool(controls)
                and bool(checks)
                and all(isinstance(item, dict) and item.get("result") == "passed" for item in checks)
                and diff_review.get("status") == "passed"
                and diff_evidence_ok
                and scanner.get("status") not in {"failed", "unverified", None}
                and dependency.get("status") not in {"failed", "unverified", None}
            )
    if not security_ok:
        reasons.append("security-evidence-incomplete")

    if not isinstance(task, dict):
        reasons.append("current-task-missing")

    if not reasons:
        status = "COMPLETE"
    elif reasons == ["runtime-verification-not-current-pass"]:
        status = "INCOMPLETE_VERIFICATION"
    elif "acceptance-evidence-incomplete" in reasons:
        status = "INCOMPLETE_ACCEPTANCE"
    elif "security-evidence-incomplete" in reasons:
        status = "INCOMPLETE_SECURITY"
    else:
        status = "INCOMPLETE"

    return stamp_artifact("completion", {
        "task_id": task_id,
        "status": status,
        "runtime_verification_ok": verification_ok,
        "acceptance_ok": acceptance_ok,
        "security_ok": security_ok,
        "security_candidate_surfaces": candidates,
        "blocking_reasons": reasons,
    })
