"""Versioned runtime artifact and configuration contracts.

The project stays standard-library-only. A small checked-in contract manifest supplies
schema versions and required top-level field types; semantic validators below enforce
the invariants that matter for workflow safety.
"""

import json
from pathlib import Path
from typing import Dict, Iterable, Optional


class ContractError(RuntimeError):
    """Raised when a runtime artifact or config violates its declared contract."""


def _schema_root() -> Path:
    # Source checkout: runtime/../schemas. Installed project: .vibe/tools/../schemas.
    return Path(__file__).resolve().parent.parent / "schemas"


def _manifest() -> Dict[str, object]:
    path = _schema_root() / "contracts-v1.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("Contract manifest is missing or invalid: {}".format(path)) from exc
    if not isinstance(data, dict) or data.get("manifest_version") != 1:
        raise ContractError("Unsupported contract manifest version.")
    return data


def _type_ok(value: object, expected: str) -> bool:
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "null":
        return value is None
    raise ContractError("Unknown contract type: {}".format(expected))


def _validate_required(label: str, data: object, required: Dict[str, object]) -> Dict[str, object]:
    if not isinstance(data, dict):
        raise ContractError("{} must be a JSON object.".format(label))
    for key, expected in required.items():
        if key not in data:
            raise ContractError("{} missing required field: {}".format(label, key))
        allowed = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(data.get(key), str(item)) for item in allowed):
            raise ContractError(
                "{}.{} has invalid type; expected {}.".format(label, key, "/".join(map(str, allowed)))
            )
    return data


def artifact_version(kind: str) -> int:
    artifacts = _manifest().get("artifacts") or {}
    spec = artifacts.get(kind) if isinstance(artifacts, dict) else None
    if not isinstance(spec, dict):
        raise ContractError("Unknown artifact contract: {}".format(kind))
    version = spec.get("version")
    if not isinstance(version, int):
        raise ContractError("Artifact contract {} has no valid version.".format(kind))
    return version


def stamp_artifact(kind: str, data: Dict[str, object]) -> Dict[str, object]:
    stamped = dict(data)
    stamped["artifact_type"] = kind
    stamped["schema_version"] = artifact_version(kind)
    validate_artifact(kind, stamped)
    return stamped


def validate_artifact(kind: str, data: object) -> Dict[str, object]:
    manifest = _manifest()
    artifacts = manifest.get("artifacts") or {}
    spec = artifacts.get(kind) if isinstance(artifacts, dict) else None
    if not isinstance(spec, dict):
        raise ContractError("Unknown artifact contract: {}".format(kind))
    required = spec.get("required") or {}
    if not isinstance(required, dict):
        raise ContractError("Artifact contract {} is malformed.".format(kind))
    value = _validate_required(kind, data, required)
    if value.get("artifact_type") != kind:
        raise ContractError(
            "{} artifact_type mismatch: {!r}.".format(kind, value.get("artifact_type"))
        )
    if value.get("schema_version") != spec.get("version"):
        raise ContractError(
            "{} schema version {} is unsupported; expected {}.".format(
                kind, value.get("schema_version"), spec.get("version")
            )
        )
    return value


def artifact_is_valid(kind: str, data: object) -> bool:
    try:
        validate_artifact(kind, data)
    except ContractError:
        return False
    return True


def validate_config(data: object) -> Dict[str, object]:
    manifest = _manifest()
    spec = manifest.get("config") or {}
    if not isinstance(spec, dict):
        raise ContractError("Config contract is missing.")
    value = _validate_required("config", data, {"version": "integer"})
    supported = spec.get("supported_versions") or []
    if value["version"] not in supported:
        raise ContractError(
            "Unsupported config version {}. Supported versions: {}.".format(
                value["version"], ", ".join(str(item) for item in supported)
            )
        )
    for section in spec.get("object_sections") or []:
        if section in value and not isinstance(value[section], dict):
            raise ContractError("config.{} must be an object.".format(section))

    context = value.get("context") or {}
    if isinstance(context, dict):
        for key in ("max_dependency_depth", "max_files", "max_source_files", "max_test_files", "max_related_modules"):
            if key in context and (not isinstance(context[key], int) or isinstance(context[key], bool) or context[key] < 0):
                raise ContractError("config.context.{} must be a non-negative integer.".format(key))
        retrieval = context.get("retrieval")
        if retrieval is not None and not isinstance(retrieval, dict):
            raise ContractError("config.context.retrieval must be an object.")

    verification = value.get("verification") or {}
    if isinstance(verification, dict):
        commands = verification.get("commands", [])
        if not isinstance(commands, list):
            raise ContractError("config.verification.commands must be an array.")
        for command in commands:
            if not isinstance(command, list) or not command or not all(isinstance(item, str) for item in command):
                raise ContractError("Each verification command must be a non-empty array of strings.")

    architecture = value.get("architecture") or {}
    if isinstance(architecture, dict) and "profile" in architecture:
        if architecture["profile"] not in {"auto", "simple", "standard", "strict"}:
            raise ContractError("config.architecture.profile is unsupported.")

    return value


def validate_acceptance_semantics(data: Dict[str, object]) -> None:
    criteria = data.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        raise ContractError("acceptance-evidence.criteria must contain at least one criterion.")
    seen = set()
    for item in criteria:
        if not isinstance(item, dict):
            raise ContractError("Each acceptance criterion must be an object.")
        criterion_id = item.get("id")
        if not isinstance(criterion_id, str) or not criterion_id.strip() or criterion_id in seen:
            raise ContractError("Acceptance criterion ids must be unique non-empty strings.")
        seen.add(criterion_id)
        if item.get("result") not in {"met", "unmet", "unverified"}:
            raise ContractError("Acceptance criterion result must be met, unmet, or unverified.")
        if not isinstance(item.get("expected"), str) or not item.get("expected").strip():
            raise ContractError("Acceptance criterion expected result must be non-empty.")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not all(isinstance(value, str) for value in evidence):
            raise ContractError("Acceptance criterion evidence must be an array of strings.")


def validate_security_semantics(data: Dict[str, object]) -> None:
    classification = data.get("classification")
    if classification not in {"security-sensitive", "not-security-sensitive"}:
        raise ContractError("Security classification must be security-sensitive or not-security-sensitive.")
    for key in ("surfaces", "trust_boundaries", "limitations"):
        value = data.get(key)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ContractError("security-evidence.{} must be an array of strings.".format(key))
    checks = data.get("targeted_checks")
    if not isinstance(checks, list):
        raise ContractError("security-evidence.targeted_checks must be an array.")
    for item in checks:
        if not isinstance(item, dict) or item.get("result") not in {"passed", "failed", "unverified"}:
            raise ContractError("Each targeted security check needs result passed/failed/unverified.")
    for key in ("scanner", "dependency_vulnerability"):
        item = data.get(key)
        if not isinstance(item, dict):
            raise ContractError("security-evidence.{} must be an object.".format(key))
        if item.get("status") not in {
            "passed", "failed", "unverified", "not-available", "not-configured", "not-applicable"
        }:
            raise ContractError("security-evidence.{}.status is invalid.".format(key))
