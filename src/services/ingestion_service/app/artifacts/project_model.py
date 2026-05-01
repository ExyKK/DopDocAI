import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from app.artifacts.models import BuiltAnalysisArtifact, analysis_artifact_storage_key

PROJECT_MODEL_ARTIFACT_KIND = "project_model"
PROJECT_MODEL_SCHEMA_VERSION = 1

_HTTP_IMPORTS = {
    "net/http": "net_http",
    "github.com/gin-gonic/gin": "gin",
    "github.com/go-chi/chi": "chi",
    "github.com/go-chi/chi/v5": "chi",
    "github.com/labstack/echo": "echo",
    "github.com/labstack/echo/v4": "echo",
    "github.com/gofiber/fiber": "fiber",
    "github.com/gofiber/fiber/v2": "fiber",
    "github.com/gorilla/mux": "gorilla_mux",
}
_HTTP_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}
_HTTP_HANDLE_RE = re.compile(r"\bhttp\.Handle(?:Func)?\s*\(\s*([\"`])([^\"`]+)\1")
_HTTP_METHOD_CALL_RE = re.compile(
    r"\.(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS|Get|Post|Put|Delete|Patch|Head|Options)\s*"
    r"\(\s*([\"`])([^\"`]+)\2"
)
_HTTP_METHOD_FUNC_RE = re.compile(
    r"\.(?:Method|MethodFunc|HandleFunc)\s*\(\s*([\"`])([A-Z]+)\1\s*,\s*([\"`])([^\"`]+)\3"
)


def build_project_model_artifact(
    repo_path: str | Path,
    repository_id: str,
    snapshot_id: str,
    snapshot_metadata: dict[str, Any],
    file_inventory_artifact: BuiltAnalysisArtifact | dict[str, Any],
    go_symbols_artifact: BuiltAnalysisArtifact | dict[str, Any],
    package_graph_artifact: BuiltAnalysisArtifact | dict[str, Any],
    config_inventory_artifact: BuiltAnalysisArtifact | dict[str, Any],
) -> BuiltAnalysisArtifact:
    repo_root = Path(repo_path)
    file_inventory = _load_artifact_document(file_inventory_artifact)
    go_symbols = _load_artifact_document(go_symbols_artifact)
    package_graph = _load_artifact_document(package_graph_artifact)
    config_inventory = _load_artifact_document(config_inventory_artifact)

    repository_layout = _build_repository_layout(file_inventory)
    package_model = _build_package_model(package_graph)
    symbol_model = _build_symbol_model(go_symbols)
    configuration_model = _build_configuration_model(config_inventory)
    external_integrations = _detect_external_integrations(package_graph, config_inventory)
    http_surface = _detect_http_surface(repo_root, package_graph)

    summary = {
        "files_total": file_inventory.get("summary", {}).get("files_total", snapshot_metadata["files_total"]),
        "go_files_total": file_inventory.get("summary", {}).get("go_files_total", snapshot_metadata["go_files_total"]),
        "packages_total": package_graph.get("summary", {}).get("packages_total", 0),
        "symbols_total": go_symbols.get("summary", {}).get("symbols_total", 0),
        "entrypoint_packages_total": package_graph.get("summary", {}).get("entrypoint_packages_total", 0),
        "config_items_total": config_inventory.get("summary", {}).get("configuration_items_total", 0),
        "external_integrations_total": len(external_integrations),
        "http_surface_detected": http_surface["detected"],
        "http_routes_total": len(http_surface["routes"]),
        "has_tests": repository_layout["has_tests"],
        "has_generated_code": repository_layout["has_generated_code"],
    }

    document = {
        "artifact_kind": PROJECT_MODEL_ARTIFACT_KIND,
        "schema_version": PROJECT_MODEL_SCHEMA_VERSION,
        "snapshot": {
            "branch_name": snapshot_metadata["branch_name"],
            "commit_sha": snapshot_metadata["commit_sha"],
            "tree_hash": snapshot_metadata["tree_hash"],
        },
        "summary": summary,
        "repository_layout": repository_layout,
        "module": package_graph.get("module"),
        "package_topology": package_model,
        "symbols": symbol_model,
        "configuration": configuration_model,
        "external_integrations": external_integrations,
        "http_surface": http_surface,
        "source_artifacts": _source_artifacts(
            file_inventory_artifact,
            go_symbols_artifact,
            package_graph_artifact,
            config_inventory_artifact,
        ),
    }

    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum_sha256 = hashlib.sha256(payload).hexdigest()

    return BuiltAnalysisArtifact(
        artifact_kind=PROJECT_MODEL_ARTIFACT_KIND,
        schema_version=PROJECT_MODEL_SCHEMA_VERSION,
        format="json",
        content_type="application/json",
        storage_key=analysis_artifact_storage_key(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            artifact_kind=PROJECT_MODEL_ARTIFACT_KIND,
            schema_version=PROJECT_MODEL_SCHEMA_VERSION,
        ),
        checksum_sha256=checksum_sha256,
        size_bytes=len(payload),
        row_count=summary["files_total"],
        payload=payload,
        summary=summary,
    )


def _load_artifact_document(artifact: BuiltAnalysisArtifact | dict[str, Any]) -> dict[str, Any]:
    if isinstance(artifact, BuiltAnalysisArtifact):
        return json.loads(artifact.payload.decode("utf-8"))

    return artifact


def _build_repository_layout(file_inventory: dict[str, Any]) -> dict[str, Any]:
    files = file_inventory.get("files", [])
    kind_counts = Counter(item.get("kind", "other") for item in files)
    top_level: defaultdict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "path": "",
            "files_total": 0,
            "bytes_total": 0,
            "kind_counts": Counter(),
        }
    )
    key_files: list[dict[str, Any]] = []

    for file_record in files:
        path = file_record["path"]
        parts = PurePosixPath(path).parts
        top = parts[0] if len(parts) > 1 else "."
        bucket = top_level[top]
        bucket["path"] = top
        bucket["files_total"] += 1
        bucket["bytes_total"] += file_record.get("size_bytes", 0)
        bucket["kind_counts"][file_record.get("kind", "other")] += 1

        if _is_key_file(path, file_record.get("kind")):
            key_files.append(
                {
                    "path": path,
                    "kind": file_record.get("kind"),
                    "size_bytes": file_record.get("size_bytes", 0),
                    "line_count": file_record.get("line_count", 0),
                }
            )

    directories = [
        {
            "path": value["path"],
            "files_total": value["files_total"],
            "bytes_total": value["bytes_total"],
            "kind_counts": dict(sorted(value["kind_counts"].items())),
        }
        for value in top_level.values()
    ]
    directories.sort(key=lambda item: (item["path"] != ".", item["path"]))
    key_files.sort(key=lambda item: item["path"])

    return {
        "files_total": len(files),
        "bytes_total": file_inventory.get("summary", {}).get("bytes_total", 0),
        "kind_counts": dict(sorted(kind_counts.items())),
        "top_level_directories": directories,
        "key_files": key_files,
        "has_tests": kind_counts.get("test", 0) > 0 or any(item.get("is_test") for item in files),
        "has_generated_code": kind_counts.get("generated", 0) > 0 or any(item.get("is_generated") for item in files),
        "has_vendor": kind_counts.get("vendor", 0) > 0 or any(item.get("is_vendor") for item in files),
    }


def _build_package_model(package_graph: dict[str, Any]) -> dict[str, Any]:
    packages = [_compact_package(package) for package in package_graph.get("packages", [])]
    packages.sort(key=lambda item: item["package_id"])
    edges = [_compact_edge(edge) for edge in package_graph.get("edges", [])]
    edges.sort(key=lambda item: (item["from_package_id"], item["kind"], item["import_path"]))

    return {
        "summary": package_graph.get("summary", {}),
        "packages": packages,
        "edges": edges,
        "entrypoints": package_graph.get("entrypoints", []),
    }


def _compact_package(package: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_id": package["package_id"],
        "name": package["name"],
        "dir_path": package["dir_path"],
        "import_path": package.get("import_path"),
        "files_total": package.get("files_total", 0),
        "symbols_total": package.get("symbols_total", 0),
        "is_command": package.get("is_command", False),
        "is_entrypoint": package.get("is_entrypoint", False),
        "entrypoint_kind": package.get("entrypoint_kind"),
        "internal_imports": package.get("internal_imports", []),
        "external_imports": package.get("external_imports", []),
        "standard_library_imports": package.get("standard_library_imports", []),
        "has_test_files": package.get("has_test_files", False),
        "has_parse_errors": package.get("has_parse_errors", False),
    }


def _compact_edge(edge: dict[str, Any]) -> dict[str, Any]:
    return {
        "from_package_id": edge["from_package_id"],
        "to_package_id": edge.get("to_package_id"),
        "import_path": edge["import_path"],
        "kind": edge["kind"],
        "files": edge.get("files", []),
    }


def _build_symbol_model(go_symbols: dict[str, Any]) -> dict[str, Any]:
    by_kind = Counter()
    by_package = Counter()
    symbols: list[dict[str, Any]] = []

    for symbol in go_symbols.get("symbols", []):
        by_kind[symbol["kind"]] += 1
        if symbol.get("package"):
            by_package[symbol["package"]] += 1
        symbols.append(
            {
                "symbol_id": symbol["symbol_id"],
                "kind": symbol["kind"],
                "qualified_name": symbol["qualified_name"],
                "name": symbol["name"],
                "package": symbol.get("package"),
                "file_path": symbol["file_path"],
                "start_line": symbol["start_line"],
                "end_line": symbol["end_line"],
                "signature": symbol.get("signature"),
                "exported": symbol.get("exported", False),
                "is_test": symbol.get("is_test", False),
                "is_generated": symbol.get("is_generated", False),
            }
        )

    symbols.sort(key=lambda item: (item["file_path"], item["start_line"], item["qualified_name"]))
    return {
        "summary": {
            "symbols_total": len(symbols),
            "kind_counts": dict(sorted(by_kind.items())),
            "package_counts": dict(sorted(by_package.items())),
        },
        "symbols": symbols,
    }


def _build_configuration_model(config_inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": config_inventory.get("summary", {}),
        "env_vars": config_inventory.get("env_vars", []),
        "flags": config_inventory.get("flags", []),
        "config_structs": config_inventory.get("config_structs", []),
        "config_files": config_inventory.get("config_files", []),
    }


def _detect_external_integrations(
    package_graph: dict[str, Any],
    config_inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in package_graph.get("edges", []):
        import_path = edge["import_path"]
        if import_path == "net/http":
            continue

        category = _integration_category(import_path)
        if category is None:
            continue

        key = (category, import_path)
        item = candidates.setdefault(
            key,
            {
                "category": category,
                "name": _integration_name(import_path),
                "import_path": import_path,
                "source": "package_import",
                "files": set(),
            },
        )
        item["files"].update(edge.get("files", []))

    for env_var in config_inventory.get("env_vars", []):
        category = _integration_category(env_var["key"])
        if category is None:
            continue

        key = (category, env_var["key"])
        candidates[key] = {
            "category": category,
            "name": env_var["key"],
            "import_path": None,
            "source": "env_var",
            "files": {env_var["source"]["file_path"]},
        }

    integrations = []
    for item in candidates.values():
        integrations.append(
            {
                **item,
                "files": sorted(item["files"]),
            }
        )

    integrations.sort(key=lambda item: (item["category"], item["name"], item["import_path"] or ""))
    return integrations


def _detect_http_surface(repo_root: Path, package_graph: dict[str, Any]) -> dict[str, Any]:
    http_imports: dict[str, set[str]] = defaultdict(set)
    for package in package_graph.get("packages", []):
        for import_path in package.get("standard_library_imports", []) + package.get("external_imports", []):
            framework = _HTTP_IMPORTS.get(import_path)
            if framework is not None:
                for file_path in package.get("files", []):
                    http_imports[file_path].add(framework)

    routes: list[dict[str, Any]] = []
    for file_path, frameworks in sorted(http_imports.items()):
        source_path = repo_root / file_path
        if not source_path.exists():
            continue

        lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
        for line_number, line in enumerate(lines, start=1):
            routes.extend(_extract_http_routes(file_path, line_number, line, sorted(frameworks)))

    routes.sort(key=lambda item: (item["file_path"], item["line"], item["method"], item["path"]))
    frameworks = sorted({framework for values in http_imports.values() for framework in values})
    detected = bool(routes) or any(framework != "net_http" for framework in frameworks)
    confidence = "high" if routes else "medium" if detected else "none"

    return {
        "detected": detected,
        "confidence": confidence,
        "frameworks": frameworks,
        "routes": routes,
    }


def _extract_http_routes(
    file_path: str,
    line_number: int,
    line: str,
    frameworks: list[str],
) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []

    for match in _HTTP_HANDLE_RE.finditer(line):
        routes.append(
            {
                "method": None,
                "path": match.group(2),
                "framework": "net_http",
                "file_path": file_path,
                "line": line_number,
            }
        )

    for match in _HTTP_METHOD_CALL_RE.finditer(line):
        method = match.group(1).upper()
        if method in _HTTP_METHODS:
            routes.append(
                {
                    "method": method,
                    "path": match.group(3),
                    "framework": _preferred_framework(frameworks),
                    "file_path": file_path,
                    "line": line_number,
                }
            )

    for match in _HTTP_METHOD_FUNC_RE.finditer(line):
        routes.append(
            {
                "method": match.group(2),
                "path": match.group(4),
                "framework": _preferred_framework(frameworks),
                "file_path": file_path,
                "line": line_number,
            }
        )

    return routes


def _source_artifacts(*artifacts: BuiltAnalysisArtifact | dict[str, Any]) -> list[dict[str, Any]]:
    items = []
    for artifact in artifacts:
        if isinstance(artifact, BuiltAnalysisArtifact):
            items.append(
                {
                    "artifact_kind": artifact.artifact_kind,
                    "schema_version": artifact.schema_version,
                    "storage_key": artifact.storage_key,
                    "checksum_sha256": artifact.checksum_sha256,
                }
            )
        else:
            items.append(
                {
                    "artifact_kind": artifact.get("artifact_kind"),
                    "schema_version": artifact.get("schema_version"),
                    "storage_key": None,
                    "checksum_sha256": None,
                }
            )

    return items


def _is_key_file(path: str, kind: str | None) -> bool:
    name = PurePosixPath(path).name.lower()
    return (
        kind in {"markdown", "config"}
        or name in {"go.mod", "go.sum", "dockerfile", "makefile"}
        or name.startswith("docker-compose")
    )


def _integration_category(value: str) -> str | None:
    normalized = value.lower()
    if any(token in normalized for token in ("database", "postgres", "pgx", "mysql", "sqlite", "mongo", "database/sql", "gorm")):
        return "database"
    if any(token in normalized for token in ("redis", "memcache")):
        return "cache"
    if any(token in normalized for token in ("kafka", "amqp", "rabbitmq", "nats")):
        return "messaging"
    if any(token in normalized for token in ("grpc", "net/http", "gin-gonic", "go-chi", "echo", "fiber", "gorilla/mux")):
        return "network"
    if any(token in normalized for token in ("prometheus", "opentelemetry", "otel")):
        return "observability"
    if any(token in normalized for token in ("aws", "google.golang.org/api", "azure")):
        return "cloud"
    return None


def _integration_name(import_path: str) -> str:
    if import_path == "net/http":
        return "net/http"

    framework = _HTTP_IMPORTS.get(import_path)
    if framework is not None:
        return framework

    return import_path.rstrip("/").rsplit("/", 1)[-1]


def _preferred_framework(frameworks: list[str]) -> str | None:
    for framework in frameworks:
        if framework != "net_http":
            return framework

    return frameworks[0] if frameworks else None
