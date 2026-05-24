from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RepositoryClassification:
    repository_kind: str
    confidence: float
    signals: dict[str, Any]
    scores: dict[str, float]
    reasoning: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_kind": self.repository_kind,
            "confidence": self.confidence,
            "signals": self.signals,
            "scores": self.scores,
            "reasoning": self.reasoning,
        }


def classify_repository(artifacts: dict[str, Any]) -> RepositoryClassification:
    project_model = artifacts.get("project_model") or {}
    package_graph = artifacts.get("package_graph") or {}
    config_inventory = artifacts.get("config_inventory") or {}

    workspace_units = _as_dicts(project_model.get("workspace_units"))
    packages = _as_dicts(package_graph.get("packages"))
    modules = _as_dicts(package_graph.get("modules"))
    project_summary = project_model.get("summary") if isinstance(project_model.get("summary"), dict) else {}
    package_summary = package_graph.get("summary") if isinstance(package_graph.get("summary"), dict) else {}
    config_summary = config_inventory.get("summary") if isinstance(config_inventory.get("summary"), dict) else {}
    http_surface = project_model.get("http_surface") if isinstance(project_model.get("http_surface"), dict) else {}

    frontend_units = [unit for unit in workspace_units if _is_frontend_unit(unit)]
    backend_units = [unit for unit in workspace_units if _is_backend_unit(unit)]
    infra_units = [unit for unit in workspace_units if _has_role(unit, "infra")]
    go_units = [unit for unit in workspace_units if "go" in _lower_list(unit.get("languages"))]
    frontend_manifests = _frontend_manifest_count(workspace_units)
    entrypoint_packages_total = _int(
        package_summary.get("entrypoint_packages_total"),
        project_summary.get("entrypoint_packages_total"),
    )
    http_routes_total = _int(
        project_summary.get("http_routes_total"),
        http_surface.get("routes_total"),
        len(_as_dicts(http_surface.get("routes"))),
    )
    api_specs_total = _int(config_summary.get("api_specs_total"))
    go_modules_total = _int(package_summary.get("modules_total"), len(modules))
    packages_total = _int(package_summary.get("packages_total"), len(packages))
    has_go = bool(go_units or packages_total or go_modules_total)
    has_tests = bool(project_summary.get("has_tests")) or _any_path_contains(project_model, "_test.")
    has_cobra_terms = _contains_terms(
        [project_model, package_graph, config_inventory],
        {"cobra", "command", "commands", "completion", "completions", "flag", "pflag"},
    )

    signals = {
        "workspace_units_total": len(workspace_units),
        "frontend_units_total": len(frontend_units),
        "backend_units_total": len(backend_units),
        "infra_units_total": len(infra_units),
        "go_units_total": len(go_units),
        "go_modules_total": go_modules_total,
        "packages_total": packages_total,
        "entrypoint_packages_total": entrypoint_packages_total,
        "http_routes_total": http_routes_total,
        "api_specs_total": api_specs_total,
        "frontend_manifests_total": frontend_manifests,
        "has_go": has_go,
        "has_tests": has_tests,
        "has_cobra_terms": has_cobra_terms,
    }

    scores = {
        "monorepo_web_app": 0.0,
        "backend_service": 0.0,
        "frontend_app": 0.0,
        "cli_tool": 0.0,
        "library": 0.0,
        "mixed": 0.05,
    }
    reasoning: list[str] = []

    if frontend_units:
        scores["frontend_app"] += 0.35
        scores["monorepo_web_app"] += 0.25
        reasoning.append("frontend workspace unit detected")
    if backend_units:
        scores["backend_service"] += 0.35
        scores["monorepo_web_app"] += 0.25
        reasoning.append("backend workspace unit detected")
    if frontend_units and backend_units:
        scores["monorepo_web_app"] += 0.35
        reasoning.append("frontend and backend units coexist")
    if len(workspace_units) >= 3 or go_modules_total >= 2:
        scores["monorepo_web_app"] += 0.15
        scores["mixed"] += 0.1
        reasoning.append("multiple workspace units/modules detected")
    if http_routes_total > 0:
        scores["backend_service"] += 0.2
        scores["monorepo_web_app"] += 0.15
        reasoning.append("HTTP surface detected")
    if api_specs_total > 0:
        scores["backend_service"] += 0.1
        scores["monorepo_web_app"] += 0.1
        reasoning.append("API specs detected")
    if frontend_manifests > 0:
        scores["frontend_app"] += 0.25
        scores["monorepo_web_app"] += 0.15
        reasoning.append("frontend package manifest detected")
    if entrypoint_packages_total > 0 and http_routes_total == 0 and not frontend_units:
        scores["cli_tool"] += 0.45
        reasoning.append("entrypoint packages without HTTP/frontend signals detected")
    if has_go and http_routes_total == 0 and not frontend_units and not backend_units:
        scores["library"] += 0.45
        reasoning.append("Go packages without app/service workspace signals detected")
    if has_cobra_terms and not frontend_units:
        scores["library"] += 0.2
        scores["cli_tool"] += 0.15
        reasoning.append("Cobra/CLI API terms detected")
    if has_go and has_tests:
        scores["library"] += 0.05
        reasoning.append("Go tests detected")
    if frontend_units and not backend_units and http_routes_total == 0:
        scores["frontend_app"] += 0.2
    if backend_units and not frontend_units:
        scores["backend_service"] += 0.15

    repository_kind = max(scores, key=scores.get)
    top_score = scores[repository_kind]
    second_score = max(score for kind, score in scores.items() if kind != repository_kind)
    confidence = max(0.2, min(0.95, 0.55 + (top_score - second_score)))
    if top_score < 0.25:
        repository_kind = "mixed"
        confidence = 0.35
        reasoning.append("no strong type-specific signals detected")

    return RepositoryClassification(
        repository_kind=repository_kind,
        confidence=round(confidence, 3),
        signals=signals,
        scores={key: round(value, 3) for key, value in sorted(scores.items())},
        reasoning=reasoning,
    )


def _is_frontend_unit(unit: dict[str, Any]) -> bool:
    frameworks = set(_lower_list(unit.get("frameworks")))
    roles = set(_lower_list(unit.get("roles")))
    root_path = str(unit.get("root_path") or "").lower()
    return (
        "frontend" in roles
        or unit.get("unit_kind") == "frontend"
        or root_path.startswith("frontend")
        or bool(frameworks & {"react", "vite", "vue", "next", "svelte", "angular"})
        or _has_manifest(unit, "package.json")
    )


def _is_backend_unit(unit: dict[str, Any]) -> bool:
    frameworks = set(_lower_list(unit.get("frameworks")))
    roles = set(_lower_list(unit.get("roles")))
    root_path = str(unit.get("root_path") or "").lower()
    return (
        "backend" in roles
        or unit.get("unit_kind") == "backend"
        or root_path.startswith("backend")
        or bool(frameworks & {"gin", "chi", "echo", "fiber", "net_http"})
    )


def _has_role(unit: dict[str, Any], role: str) -> bool:
    return role in set(_lower_list(unit.get("roles"))) or unit.get("unit_kind") == role


def _frontend_manifest_count(workspace_units: list[dict[str, Any]]) -> int:
    return sum(1 for unit in workspace_units if _has_manifest(unit, "package.json"))


def _has_manifest(unit: dict[str, Any], name: str) -> bool:
    manifest_paths = unit.get("manifest_paths") or []
    if any(str(path).lower().endswith(name) for path in manifest_paths):
        return True
    return any(
        str(item.get("path") or item.get("file_path") or "").lower().endswith(name)
        for item in _as_dicts(unit.get("key_files"))
    )


def _any_path_contains(value: Any, needle: str) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"path", "file_path"} and needle in str(item).lower():
                return True
            if _any_path_contains(item, needle):
                return True
    elif isinstance(value, list):
        return any(_any_path_contains(item, needle) for item in value[:200])
    return False


def _contains_terms(values: list[Any], terms: set[str]) -> bool:
    seen = 0
    stack = list(values)
    while stack and seen < 1500:
        value = stack.pop()
        seen += 1
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value[:100])
        elif isinstance(value, str):
            lowered = value.lower()
            if any(term in lowered for term in terms):
                return True
    return False


def _as_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _lower_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).lower() for item in value if item is not None]


def _int(*values: Any) -> int:
    for value in values:
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0
