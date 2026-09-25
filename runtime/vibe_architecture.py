"""Architecture policy for greenfield and evolving projects.

Default:
- feature-first
- modular layered
- framework-native conventions
- clean-code rules

Strict projects switch to a Clean/Hexagonal shape only when explicitly requested
or when deterministic size thresholds are crossed.
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from vibe_stacks import IGNORE_DIRS, detect_stack, task_aware_stack

SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".php", ".java", ".kt", ".kts", ".go", ".rs", ".cs", ".rb", ".vue", ".svelte",
}

CLEAN_CODE_RULES = [
    "Use intent-revealing names; avoid vague names such as data, temp, helper, manager unless the role is genuinely generic.",
    "Keep functions focused on one main responsibility; extract only when it improves clarity or reuse.",
    "Prefer guard clauses/early returns when they reduce nesting and improve readability.",
    "Keep transport/UI handlers thin; place non-trivial business behavior in application/domain code.",
    "Do not hide failures: preserve error context and never silently swallow exceptions.",
    "Avoid hidden global mutable state; make important dependencies explicit.",
    "Reuse existing abstractions before creating new ones; avoid speculative interfaces and premature generalization.",
    "Keep modules cohesive and boundaries explicit; avoid god services/modules and circular dependencies.",
    "Keep configuration and secrets outside business logic; never hardcode secrets.",
    "Test observable behavior and important edge cases rather than coupling tests to implementation details.",
    "Comments should explain why, constraints, or non-obvious tradeoffs rather than narrating obvious code.",
    "Prefer simple code over clever code; optimize only with evidence.",
]

STANDARD_DEPENDENCY_RULES = [
    "Presentation/transport may depend on application services.",
    "Application services may orchestrate domain behavior and repository/port abstractions.",
    "Domain/business rules should not depend on controllers, routes, views, or UI concerns.",
    "Infrastructure/data access should not depend on presentation/transport code.",
    "Cross-feature access should prefer a public service/contract over importing another feature's internals.",
]

STRICT_DEPENDENCY_RULES = [
    "Domain is framework-independent and depends on no infrastructure or transport layer.",
    "Application/use-cases depend on domain and ports, not concrete infrastructure.",
    "Infrastructure implements ports owned by application/domain boundaries.",
    "Presentation depends inward on application/use-cases.",
    "Dependencies point inward; framework-specific code stays at the edges.",
]

FRAMEWORK_GUIDANCE = {
    "flask": {
        "standard": ["feature package", "blueprint/router", "service/application", "repository/data adapter when needed", "tests"],
        "strict": ["feature package", "presentation blueprint", "application use-cases + ports", "domain", "infrastructure adapters", "tests"],
        "notes": ["Keep Flask globals/request objects out of core business logic.", "Use repositories only when data-access complexity justifies them."],
    },
    "fastapi": {
        "standard": ["feature package", "router", "service/application", "repository/data adapter", "schemas", "tests"],
        "strict": ["feature package", "presentation router + transport schemas", "application use-cases + ports", "domain", "infrastructure adapters", "tests"],
        "notes": ["Keep Pydantic transport schemas separate from complex domain behavior.", "Treat Depends-based wiring as edge composition."],
    },
    "django": {
        "standard": ["Django app per feature", "urls/views", "service/application for non-trivial workflows", "models/data access", "tests"],
        "strict": ["Django app/feature", "presentation urls/views", "application use-cases + ports", "domain", "Django ORM/infrastructure adapters", "tests"],
        "notes": ["Follow Django app conventions first.", "Do not add repository wrappers around trivial ORM access without a reason."],
    },
    "express": {
        "standard": ["feature module", "routes", "controller", "service/application", "repository/data adapter when needed", "tests"],
        "strict": ["feature module", "presentation routes/controllers", "application use-cases + ports", "domain", "infrastructure adapters", "tests"],
        "notes": ["Keep middleware/order explicit.", "Do not put business logic in route handlers."],
    },
    "nestjs": {
        "standard": ["feature module", "controller", "service", "providers/repository", "dto", "tests"],
        "strict": ["feature module", "presentation controller", "application use-cases + ports", "domain", "Nest/infrastructure providers", "tests"],
        "notes": ["Keep Nest module/provider conventions.", "Use DI tokens/ports at real boundaries, not for every class."],
    },
    "react": {
        "standard": ["app/router shell", "feature modules", "components", "hooks/state", "api/data adapters", "tests"],
        "strict": ["app/router shell", "feature presentation", "application/use-cases", "domain where business-heavy", "api/state adapters", "tests"],
        "notes": ["Prefer feature-first UI modules.", "Keep non-trivial workflows out of presentational components.", "Shared modules must not depend on feature internals."],
    },
    "vue": {
        "standard": ["app/router shell", "feature modules", "Vue components", "composables/stores", "api/data adapters", "tests"],
        "strict": ["app/router shell", "feature presentation", "application/use-cases", "domain where business-heavy", "Pinia/API adapters", "tests"],
        "notes": ["Keep SFCs focused on presentation and local interaction.", "Keep reusable workflows in composables/services rather than page components."],
    },
    "nuxt": {
        "standard": ["pages/layouts shell", "feature modules", "components/composables", "server routes", "data adapters", "tests"],
        "strict": ["pages/layouts shell", "feature presentation", "application/use-cases", "domain where business-heavy", "server/client adapters", "tests"],
        "notes": ["Respect Nuxt file-system routing and server/client boundaries.", "Treat server routes and runtime config as edge concerns."],
    },
    "svelte": {
        "standard": ["app shell", "feature modules", "Svelte components", "stores/actions", "api/data adapters", "tests"],
        "strict": ["app shell", "feature presentation", "application/use-cases", "domain where business-heavy", "store/API adapters", "tests"],
        "notes": ["Keep components focused on UI behavior.", "Keep reusable workflows out of component files when they become non-trivial."],
    },
    "sveltekit": {
        "standard": ["routes/layout shell", "feature modules", "components/stores", "load/actions/server routes", "data adapters", "tests"],
        "strict": ["routes/layout shell", "feature presentation", "application/use-cases", "domain where business-heavy", "server/client adapters", "tests"],
        "notes": ["Respect +page/+layout/+server boundaries.", "Keep business logic out of route transport files and server actions where practical."],
    },
    "vite": {
        "standard": ["framework app shell", "feature modules", "shared UI/utilities", "api/data adapters", "tests"],
        "strict": ["framework app shell", "feature presentation", "application/use-cases", "domain where justified", "edge adapters", "tests"],
        "notes": ["Vite is tooling, not a domain architecture.", "Let the React/Vue/Svelte adapter determine UI structure when one is present."],
    },
    "nextjs": {
        "standard": ["route/page shell", "feature module", "application/service logic", "data/client adapters", "components", "tests"],
        "strict": ["route/page shell", "feature presentation", "application use-cases + ports", "domain where business-heavy", "server/client infrastructure adapters", "tests"],
        "notes": ["Respect server/client component boundaries.", "Keep reusable business behavior out of page components."],
    },
    "wordpress": {
        "standard": ["WordPress entry/hooks", "feature-oriented plugin/theme modules", "services/business logic", "WordPress data/API adapters", "templates/blocks/assets", "tests"],
        "strict": ["WordPress hooks/REST/templates at the edge", "application use-cases + ports", "domain", "WordPress infrastructure adapters", "blocks/assets", "tests"],
        "notes": ["Never modify WordPress core for application behavior.", "Treat hooks, filters, shortcodes, REST routes, options/meta and block contracts as integration boundaries.", "Keep theme templates focused on presentation and move reusable business behavior into plugin/feature modules."],
    },
    "laravel": {
        "standard": ["framework routes", "controllers/requests", "feature/service/application", "models or repositories when justified", "policies/jobs/events", "tests"],
        "strict": ["framework routes/controllers", "application use-cases + ports", "domain", "Laravel infrastructure adapters", "policies/jobs/events", "tests"],
        "notes": ["Follow Laravel conventions before generic Clean Architecture conventions.", "Do not create a repository for every Eloquent model by default."],
    },
    "rails": {
        "standard": ["Rails routes", "controllers", "models/ActiveRecord", "services for non-trivial workflows", "jobs/mailers/policies", "tests"],
        "strict": ["Rails routes/controllers", "application use-cases + ports", "domain", "ActiveRecord/infrastructure adapters", "jobs/mailers/policies", "tests"],
        "notes": ["Follow Rails conventions and Zeitwerk autoloading before generic architecture ceremony.", "Do not wrap every ActiveRecord model in a repository by default.", "Keep callbacks and controllers thin when workflows become non-trivial."],
    },
    "spring": {
        "standard": ["package-by-feature", "controller", "service/application", "repository", "domain", "tests"],
        "strict": ["package-by-feature", "presentation controller", "application use-cases + ports", "domain", "Spring infrastructure adapters", "tests"],
        "notes": ["Prefer package-by-feature over one global package per layer.", "Use interfaces where they define meaningful boundaries."],
    },
    "gin": {
        "standard": ["feature/package", "handler/router", "service/application", "repository/data adapter", "tests"],
        "strict": ["feature/package", "presentation handler", "application use-cases + ports", "domain", "infrastructure adapters", "tests"],
        "notes": ["Keep gin.Context at the transport boundary."],
    },
    "fiber": {
        "standard": ["feature/package", "handler/router", "service/application", "repository/data adapter", "tests"],
        "strict": ["feature/package", "presentation handler", "application use-cases + ports", "domain", "infrastructure adapters", "tests"],
        "notes": ["Keep Fiber context at the transport boundary."],
    },
    "actix-web": {
        "standard": ["feature/module", "handler", "service/application", "repository/data adapter", "domain types", "tests"],
        "strict": ["feature/module", "presentation handler", "application use-cases + traits/ports", "domain", "infrastructure adapters", "tests"],
        "notes": ["Keep Actix extractors/state at the edge when business logic can remain framework-independent."],
    },
}

LANGUAGE_FALLBACK = {
    "python": ["feature package", "entrypoint/router", "service/application", "repository/data adapter when needed", "tests"],
    "javascript": ["feature module", "entrypoint/controller", "service/application", "data adapter when needed", "tests"],
    "typescript": ["feature module", "entrypoint/controller", "service/application", "data adapter when needed", "types/contracts", "tests"],
    "php": ["feature/module", "controller/entrypoint", "service/application", "model/repository when needed", "tests"],
    "java": ["package-by-feature", "controller/entrypoint", "service/application", "repository", "domain", "tests"],
    "go": ["feature/package", "handler/entrypoint", "service/application", "repository/data adapter", "tests"],
    "rust": ["feature/module", "handler/entrypoint", "service/application", "repository/adapter", "domain types", "tests"],
    "ruby": ["feature/module", "entrypoint/controller", "service/application", "model/data access when needed", "tests"],
    "generic": ["feature/module", "entrypoint", "application/service", "data/infrastructure when needed", "tests"],
}


def _read_config(root: Path) -> Dict[str, object]:
    path = root / ".vibe" / "config.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _stats_from_relative_paths(paths: List[str]) -> Dict[str, int]:
    count = 0
    feature_dirs = set()
    for value in paths:
        rel = Path(value)
        if rel.suffix.lower() not in SOURCE_EXTENSIONS:
            continue
        count += 1
        parts = rel.parts
        if len(parts) >= 2:
            if parts[0] in ("src", "app", "lib", "internal", "packages", "apps") and len(parts) >= 3:
                feature_dirs.add("/".join(parts[:2]))
            else:
                feature_dirs.add(parts[0])
    return {"source_files": count, "feature_roots": len(feature_dirs)}


def _module_key(value: str) -> str:
    parts = Path(value).parts
    if not parts:
        return ""
    if parts[0] in {"src", "app", "lib", "internal", "packages", "apps"} and len(parts) > 1:
        return "/".join(parts[:2])
    return parts[0]


def _task_scope_paths(paths: Sequence[str], target_files: Optional[Sequence[str]]) -> Dict[str, object]:
    repository_paths = [Path(value).as_posix() for value in paths]
    targets = [Path(value).as_posix() for value in (target_files or [])]
    modules = sorted({key for key in (_module_key(value) for value in targets) if key})
    if not modules:
        return {"mode": "repository", "modules": [], "paths": repository_paths}
    scoped = [value for value in repository_paths if _module_key(value) in set(modules)]
    if not scoped:
        return {"mode": "repository", "modules": modules, "paths": repository_paths}
    return {"mode": "task-modules", "modules": modules, "paths": scoped}


def _source_stats(root: Path) -> Dict[str, int]:
    paths: List[str] = []
    for current, dirs, files in os.walk(str(root)):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if name not in IGNORE_DIRS]
        for name in files:
            path = current_path / name
            if path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue
            try:
                paths.append(path.relative_to(root).as_posix())
            except ValueError:
                continue
    return _stats_from_relative_paths(paths)


def default_architecture_config() -> Dict[str, object]:
    return {
        "profile": "auto",
        "default_profile": "standard",
        "module_style": "feature-first",
        "default_pattern": "modular-layered",
        "strict_pattern": "hexagonal",
        "framework_conventions": "prefer",
        "allow_auto_strict": True,
        "strict_thresholds": {
            "source_files": 300,
            "feature_roots": 20,
        },
    }


def architecture_policy(
    root: Path,
    config: Optional[Dict[str, object]] = None,
    source_paths: Optional[List[str]] = None,
    task_request: Optional[str] = None,
    target_files: Optional[Sequence[str]] = None,
) -> Dict[str, object]:
    stack = task_aware_stack(detect_stack(root), task_request, target_files)
    full_config = config if isinstance(config, dict) else _read_config(root)
    architecture = dict(default_architecture_config())
    user_arch = full_config.get("architecture") if isinstance(full_config, dict) else None
    if isinstance(user_arch, dict):
        for key, value in user_arch.items():
            if key == "strict_thresholds" and isinstance(value, dict):
                merged = dict(architecture["strict_thresholds"])
                merged.update(value)
                architecture[key] = merged
            else:
                architecture[key] = value

    requested = str(architecture.get("profile", "auto"))
    if requested not in {"auto", "simple", "standard", "strict"}:
        requested = "auto"

    if source_paths is None:
        repository_paths: List[str] = []
        for current, dirs, files in os.walk(str(root)):
            current_path = Path(current)
            dirs[:] = [name for name in dirs if name not in IGNORE_DIRS]
            for name in files:
                path = current_path / name
                if path.suffix.lower() in SOURCE_EXTENSIONS:
                    try:
                        repository_paths.append(path.relative_to(root).as_posix())
                    except ValueError:
                        pass
    else:
        repository_paths = list(source_paths)
    repository_stats = _stats_from_relative_paths(repository_paths)
    scope = _task_scope_paths(repository_paths, target_files)
    evaluation_paths = list(scope["paths"])
    stats = _stats_from_relative_paths(evaluation_paths)
    thresholds = architecture.get("strict_thresholds") or {}
    auto_strict = bool(architecture.get("allow_auto_strict", True)) and (
        stats["source_files"] >= int(thresholds.get("source_files", 300))
        or stats["feature_roots"] >= int(thresholds.get("feature_roots", 20))
    )

    if requested == "auto":
        effective = "strict" if auto_strict else str(architecture.get("default_profile", "standard"))
    else:
        effective = requested
    if effective not in {"simple", "standard", "strict"}:
        effective = "standard"

    if effective == "strict":
        pattern = str(architecture.get("strict_pattern", "hexagonal"))
    elif effective == "simple":
        pattern = "framework-native-simple"
    else:
        pattern = str(architecture.get("default_pattern", "modular-layered"))

    frameworks = list(stack.get("frameworks") or [])
    primary = str(stack.get("primary", "generic"))
    framework_details = []
    for framework in frameworks:
        guide = FRAMEWORK_GUIDANCE.get(framework)
        if guide:
            framework_details.append({
                "framework": framework,
                "structure": guide["strict" if effective == "strict" else "standard"],
                "notes": guide.get("notes", []),
            })

    if framework_details:
        recommended_structure = framework_details[0]["structure"]
    else:
        recommended_structure = LANGUAGE_FALLBACK.get(primary, LANGUAGE_FALLBACK["generic"])

    if effective == "simple":
        recommended_structure = [
            item for item in recommended_structure
            if "repository" not in item.lower() and "port" not in item.lower()
        ]

    decision_reasons: List[str] = []
    if requested == "strict":
        decision_reasons.append("Strict profile explicitly configured.")
    elif requested == "simple":
        decision_reasons.append("Simple profile explicitly configured.")
    elif requested == "standard":
        decision_reasons.append("Standard profile explicitly configured.")
    elif auto_strict:
        decision_reasons.append(
            "Auto profile promoted to strict because the evaluated architecture scope crossed configured thresholds."
        )
    else:
        decision_reasons.append(
            "Auto profile uses standard by default; the evaluated architecture scope has not crossed strict thresholds."
        )

    return {
        "requested_profile": requested,
        "effective_profile": effective,
        "pattern": pattern,
        "module_style": "feature-first",
        "framework_conventions": str(architecture.get("framework_conventions", "prefer")),
        "stack": stack,
        "project_size": repository_stats,
        "evaluation_size": stats,
        "architecture_scope": {
            "mode": scope["mode"],
            "modules": scope["modules"],
            "target_files": [Path(value).as_posix() for value in (target_files or [])],
        },
        "strict_thresholds": thresholds,
        "auto_strict_triggered": auto_strict,
        "decision_reasons": decision_reasons,
        "recommended_structure": recommended_structure,
        "framework_guidance": framework_details,
        "dependency_rules": STRICT_DEPENDENCY_RULES if effective == "strict" else STANDARD_DEPENDENCY_RULES,
        "clean_code_rules": CLEAN_CODE_RULES,
        "principles": [
            "Framework conventions first.",
            "Feature-first organization by default.",
            "Modular layered architecture for standard projects.",
            "Use Clean/Hexagonal boundaries only for strict projects or when complexity justifies them.",
            "Abstraction only when justified by a real boundary, variation, reuse, or test seam.",
        ],
    }
