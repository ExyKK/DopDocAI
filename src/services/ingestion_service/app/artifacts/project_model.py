import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from app.artifacts.models import BuiltAnalysisArtifact, analysis_artifact_storage_key
from app.artifacts.source_scope import (
    SOURCE_SCOPE_INFRA,
    SOURCE_SCOPE_RUNTIME,
    runtime_scope_from_source_scope,
    source_scope_from_record,
)

PROJECT_MODEL_ARTIFACT_KIND = "project_model"
PROJECT_MODEL_SCHEMA_VERSION = 2

_MAX_IMPORTANT_PACKAGES = 20
_MAX_IMPORTANT_SYMBOLS = 40
_MAX_CONFIG_ITEMS = 50
_MAX_KEY_FILES = 40
_MAX_UNIT_KEY_FILES = 20
_MAX_DEPENDENCY_HINTS = 30

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
_HTTP_METHOD_NAMES = (
    "GET",
    "POST",
    "PUT",
    "DELETE",
    "PATCH",
    "HEAD",
    "OPTIONS",
    "Get",
    "Post",
    "Put",
    "Delete",
    "Patch",
    "Head",
    "Options",
)
_HTTP_ROUTE_METHOD_RE = re.compile(
    r"\b(?P<receiver>[A-Za-z_]\w*)\.(?P<method>"
    + "|".join(_HTTP_METHOD_NAMES)
    + r")\s*\(",
    re.DOTALL,
)
_HTTP_HANDLE_RE = re.compile(
    r"\b(?P<receiver>[A-Za-z_]\w*|http)\.(?P<method>Handle|HandleFunc)\s*\(",
    re.DOTALL,
)
_HTTP_METHOD_FUNC_RE = re.compile(
    r"\b(?P<receiver>[A-Za-z_]\w*)\.(?P<method>Method|MethodFunc)\s*\(",
    re.DOTALL,
)
_HTTP_METHODS_CHAIN_RE = re.compile(r"\.Methods\s*\((?P<args>[^)]*)\)", re.DOTALL)
_HTTP_GROUP_ASSIGN_RE = re.compile(
    r"\b(?P<target>[A-Za-z_]\w*)\s*(?::=|=)\s*(?P<base>[A-Za-z_]\w*)\."
    r"(?P<kind>Group|PathPrefix)\s*\(",
    re.DOTALL,
)
_HTTP_ROUTE_BLOCK_RE = re.compile(
    r"\b(?P<base>[A-Za-z_]\w*)\.Route\s*\(\s*(?P<quote>[\"`])(?P<prefix>.*?)(?P=quote)"
    r"\s*,\s*func\s*\(\s*(?P<target>[A-Za-z_]\w*)",
    re.DOTALL,
)
_HTTP_LITERAL_RE = re.compile(r"^\s*(?P<quote>[\"`])(?P<value>.*?)(?P=quote)\s*$", re.DOTALL)


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
    external_integrations = _detect_external_integrations(package_graph, config_inventory)
    http_surface = _detect_http_surface(repo_root, package_graph, go_symbols)
    workspace_units = _build_workspace_units(
        repo_root,
        file_inventory=file_inventory,
        package_graph=package_graph,
        http_surface=http_surface,
    )
    workspace_unit_lookup = _build_workspace_unit_lookup(workspace_units)
    go_model = _build_go_model(package_graph, workspace_unit_lookup)
    code_outline = _build_code_outline(go_symbols, go_model["important_packages"])
    configuration_model = _build_configuration_model(config_inventory)

    summary = {
        "files_total": file_inventory.get("summary", {}).get("files_total", snapshot_metadata["files_total"]),
        "bytes_total": file_inventory.get("summary", {}).get("bytes_total", snapshot_metadata["bytes_total"]),
        "go_files_total": file_inventory.get("summary", {}).get("go_files_total", snapshot_metadata["go_files_total"]),
        "workspace_units_total": len(workspace_units),
        "packages_total": package_graph.get("summary", {}).get("packages_total", 0),
        "symbols_total": go_symbols.get("summary", {}).get("symbols_total", 0),
        "runtime_symbols_total": go_symbols.get("summary", {}).get("runtime_symbols_total", 0),
        "entrypoint_packages_total": package_graph.get("summary", {}).get("entrypoint_packages_total", 0),
        "config_items_total": config_inventory.get("summary", {}).get("configuration_items_total", 0),
        "runtime_config_items_total": config_inventory.get("summary", {}).get(
            "runtime_configuration_items_total",
            config_inventory.get("summary", {}).get("configuration_items_total", 0),
        ),
        "config_files_total": config_inventory.get("summary", {}).get("config_files_total", 0),
        "api_specs_total": config_inventory.get("summary", {}).get("api_specs_total", 0),
        "external_integrations_total": len(external_integrations),
        "http_surface_detected": http_surface["detected"],
        "http_routes_total": len(http_surface["routes"]),
        "has_tests": repository_layout["has_tests"],
        "has_generated_code": repository_layout["has_generated_code"],
        "has_vendor": repository_layout["has_vendor"],
    }

    document = {
        "artifact_kind": PROJECT_MODEL_ARTIFACT_KIND,
        "schema_version": PROJECT_MODEL_SCHEMA_VERSION,
        "model_kind": "compact_project_manifest",
        "snapshot": {
            "branch_name": snapshot_metadata["branch_name"],
            "commit_sha": snapshot_metadata["commit_sha"],
            "tree_hash": snapshot_metadata["tree_hash"],
        },
        "summary": summary,
        "repository_layout": repository_layout,
        "workspace_units": workspace_units,
        "go": go_model,
        "code_outline": code_outline,
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
    _attach_budget_metadata(
        document,
        file_inventory=file_inventory,
        go_symbols=go_symbols,
        package_graph=package_graph,
        config_inventory=config_inventory,
    )

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
        row_count=summary["workspace_units_total"],
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
    source_scope_counts = Counter(source_scope_from_record(item) for item in files)
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
    key_files = key_files[:_MAX_KEY_FILES]

    return {
        "files_total": len(files),
        "bytes_total": file_inventory.get("summary", {}).get("bytes_total", 0),
        "kind_counts": dict(sorted(kind_counts.items())),
        "source_scope_counts": dict(sorted(source_scope_counts.items())),
        "top_level_directories": directories,
        "key_files": key_files,
        "has_tests": kind_counts.get("test", 0) > 0 or any(item.get("is_test") for item in files),
        "has_generated_code": kind_counts.get("generated", 0) > 0 or any(item.get("is_generated") for item in files),
        "has_vendor": kind_counts.get("vendor", 0) > 0 or any(item.get("is_vendor") for item in files),
    }


def _build_go_model(
    package_graph: dict[str, Any],
    workspace_unit_lookup: dict[str, Any],
) -> dict[str, Any]:
    packages = package_graph.get("packages", [])
    important_packages = [
        _compact_important_package(package, workspace_unit_lookup)
        for package in _important_packages(packages)
    ]
    entrypoints = [
        {
            **entrypoint,
            "workspace_unit_id": _workspace_unit_id_for_path(
                entrypoint.get("dir_path", "."),
                workspace_unit_lookup,
            ),
            "source_scope": entrypoint.get("source_scope", SOURCE_SCOPE_RUNTIME),
            "runtime_scope": entrypoint.get("runtime_scope", True),
        }
        for entrypoint in package_graph.get("entrypoints", [])
        if entrypoint.get("runtime_scope", True)
    ]
    entrypoints.sort(key=lambda item: (item["dir_path"], item["package_id"]))

    return {
        "summary": package_graph.get("summary", {}),
        "modules": _go_modules(package_graph),
        "entrypoints": entrypoints,
        "important_packages": important_packages,
        "important_packages_omitted": max(0, len(packages) - len(important_packages)),
        "dependency_summary": _go_dependency_summary(package_graph),
    }


def _important_packages(packages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(
        packages,
        key=lambda package: (
            not package.get("runtime_scope", package.get("source_scope", SOURCE_SCOPE_RUNTIME) == SOURCE_SCOPE_RUNTIME),
            not package.get("is_entrypoint", False),
            not package.get("is_command", False),
            -int(package.get("symbols_total", 0)),
            -int(package.get("files_total", 0)),
            package.get("dir_path", ""),
            package.get("package_id", ""),
        ),
    )
    return ranked[:_MAX_IMPORTANT_PACKAGES]


def _compact_important_package(
    package: dict[str, Any],
    workspace_unit_lookup: dict[str, Any],
) -> dict[str, Any]:
    return {
        "package_id": package["package_id"],
        "workspace_unit_id": _workspace_unit_id_for_path(
            package.get("dir_path", "."),
            workspace_unit_lookup,
        ),
        "name": package["name"],
        "dir_path": package["dir_path"],
        "import_path": package.get("import_path"),
        "module_root": package.get("module_root"),
        "files_total": package.get("files_total", 0),
        "symbols_total": package.get("symbols_total", 0),
        "runtime_symbols_total": package.get("runtime_symbols_total", package.get("symbols_total", 0)),
        "source_scope": package.get("source_scope", SOURCE_SCOPE_RUNTIME),
        "runtime_scope": package.get("runtime_scope", True),
        "file_source_scope_counts": package.get("file_source_scope_counts", {}),
        "is_command": package.get("is_command", False),
        "is_entrypoint": package.get("is_entrypoint", False),
        "entrypoint_kind": package.get("entrypoint_kind"),
        "external_imports": package.get("external_imports", [])[:_MAX_DEPENDENCY_HINTS],
        "standard_library_imports": package.get("standard_library_imports", [])[:_MAX_DEPENDENCY_HINTS],
        "has_test_files": package.get("has_test_files", False),
        "has_generated_files": package.get("has_generated_files", False),
        "has_parse_errors": package.get("has_parse_errors", False),
    }


def _go_modules(package_graph: dict[str, Any]) -> list[dict[str, Any]]:
    modules = package_graph.get("modules") or []
    if modules:
        return modules

    module = package_graph.get("module") or {}
    if module.get("path") or module.get("go_mod_path"):
        return [
            {
                "module_id": "go:.",
                "root_dir": ".",
                "path": module.get("path"),
                "go_version": module.get("go_version"),
                "toolchain": module.get("toolchain"),
                "go_mod_path": module.get("go_mod_path"),
            }
        ]

    return []


def _go_dependency_summary(package_graph: dict[str, Any]) -> dict[str, Any]:
    external = Counter()
    standard = Counter()
    internal = Counter()
    for package in package_graph.get("packages", []):
        if not package.get("runtime_scope", package.get("source_scope", SOURCE_SCOPE_RUNTIME) == SOURCE_SCOPE_RUNTIME):
            continue

        external.update(_package_scoped_imports(package, "runtime_external_imports", "external_imports"))
        standard.update(
            _package_scoped_imports(
                package,
                "runtime_standard_library_imports",
                "standard_library_imports",
            )
        )
        internal.update(_package_scoped_imports(package, "runtime_internal_imports", "internal_imports"))

    return {
        "external_imports_top": _counter_top(external),
        "standard_library_imports_top": _counter_top(standard),
        "internal_imports_top": _counter_top(internal),
    }


def _counter_top(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"name": name, "count": count}
        for name, count in sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:_MAX_DEPENDENCY_HINTS]
    ]


def _package_scoped_imports(
    package: dict[str, Any],
    scoped_key: str,
    fallback_key: str,
) -> list[str]:
    return package[scoped_key] if scoped_key in package else package.get(fallback_key, [])


def _build_code_outline(
    go_symbols: dict[str, Any],
    important_packages: list[dict[str, Any]],
) -> dict[str, Any]:
    important_package_dirs = {package["dir_path"] for package in important_packages}
    ranked_symbols = sorted(
        go_symbols.get("symbols", []),
        key=lambda symbol: (
            not symbol.get("runtime_scope", source_scope_from_record(symbol) == SOURCE_SCOPE_RUNTIME),
            not symbol.get("exported", False),
            PurePosixPath(symbol.get("file_path", "")).parent.as_posix() not in important_package_dirs,
            symbol.get("file_path", ""),
            symbol.get("start_line", 0),
            symbol.get("qualified_name", ""),
        ),
    )
    important_symbols = [_compact_symbol(symbol) for symbol in ranked_symbols[:_MAX_IMPORTANT_SYMBOLS]]
    symbols_total = go_symbols.get("summary", {}).get("symbols_total", len(go_symbols.get("symbols", [])))
    source_scope_counts = Counter(source_scope_from_record(symbol) for symbol in go_symbols.get("symbols", []))

    return {
        "summary": {
            **go_symbols.get("summary", {}),
            "important_symbols_total": len(important_symbols),
            "important_symbols_omitted": max(0, symbols_total - len(important_symbols)),
            "source_scope_counts": dict(sorted(source_scope_counts.items())),
        },
        "important_symbols": important_symbols,
    }


def _compact_symbol(symbol: dict[str, Any]) -> dict[str, Any]:
    return {
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
        "source_scope": source_scope_from_record(symbol),
        "runtime_scope": symbol.get("runtime_scope", runtime_scope_from_source_scope(source_scope_from_record(symbol))),
    }


def _build_configuration_model(config_inventory: dict[str, Any]) -> dict[str, Any]:
    env_vars = config_inventory.get("env_vars", [])
    flags = config_inventory.get("flags", [])
    config_structs = config_inventory.get("config_structs", [])
    config_files = config_inventory.get("config_files", [])
    primary_config_scopes = {SOURCE_SCOPE_RUNTIME, SOURCE_SCOPE_INFRA}
    runtime_env_vars = [item for item in env_vars if item.get("source_scope", SOURCE_SCOPE_RUNTIME) == SOURCE_SCOPE_RUNTIME]
    runtime_flags = [item for item in flags if item.get("source_scope", SOURCE_SCOPE_RUNTIME) == SOURCE_SCOPE_RUNTIME]
    runtime_config_structs = [
        item for item in config_structs if item.get("source_scope", SOURCE_SCOPE_RUNTIME) == SOURCE_SCOPE_RUNTIME
    ]
    primary_config_files = [
        item for item in config_files if item.get("source_scope", SOURCE_SCOPE_RUNTIME) in primary_config_scopes
    ]
    return {
        "summary": config_inventory.get("summary", {}),
        "env_vars": _sample_config_items(runtime_env_vars, key="key"),
        "env_vars_omitted": max(0, len(runtime_env_vars) - _MAX_CONFIG_ITEMS),
        "non_runtime_env_vars_total": max(0, len(env_vars) - len(runtime_env_vars)),
        "flags": _sample_config_items(runtime_flags, key="name"),
        "flags_omitted": max(0, len(runtime_flags) - _MAX_CONFIG_ITEMS),
        "non_runtime_flags_total": max(0, len(flags) - len(runtime_flags)),
        "config_structs": _compact_config_structs(runtime_config_structs),
        "config_structs_omitted": max(0, len(runtime_config_structs) - _MAX_CONFIG_ITEMS),
        "non_runtime_config_structs_total": max(0, len(config_structs) - len(runtime_config_structs)),
        "config_files": _compact_config_files(primary_config_files),
        "config_files_omitted": max(0, len(primary_config_files) - _MAX_CONFIG_ITEMS),
        "non_primary_config_files_total": max(0, len(config_files) - len(primary_config_files)),
        "api_specs": config_inventory.get("api_specs", []),
    }


def _sample_config_items(items: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
    sampled = sorted(items, key=lambda item: (str(item.get(key, "")), _source_file_path(item)))[:_MAX_CONFIG_ITEMS]
    compact: list[dict[str, Any]] = []
    for item in sampled:
        compact_item = {
            key: item.get(key),
            "required": item.get("required", False),
            "source_file_path": _source_file_path(item),
            "source_scope": item.get("source_scope", SOURCE_SCOPE_RUNTIME),
        }
        if "default_value" in item:
            compact_item["default_value"] = item.get("default_value")
        if item.get("required_reason"):
            compact_item["required_reason"] = item["required_reason"]
        compact.append(compact_item)

    return compact


def _compact_config_structs(config_structs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in sorted(config_structs, key=lambda item: (_source_file_path(item), item.get("name", "")))[:_MAX_CONFIG_ITEMS]:
        fields = item.get("fields", [])
        compact.append(
            {
                "name": item.get("name"),
                "fields_total": len(fields),
                "required_fields_total": sum(1 for field in fields if field.get("required")),
                "config_keys_total": sum(len(field.get("config_keys", [])) for field in fields),
                "source_file_path": _source_file_path(item),
                "source_scope": item.get("source_scope", SOURCE_SCOPE_RUNTIME),
            }
        )

    return compact


def _compact_config_files(config_files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact = []
    for item in sorted(config_files, key=lambda item: item.get("path", ""))[:_MAX_CONFIG_ITEMS]:
        compact.append(
            {
                "path": item.get("path"),
                "format": item.get("format"),
                "keys_total": len(item.get("keys", [])),
                "parse_error": item.get("parse_error", False),
                "truncated": item.get("truncated", False),
                "truncation_reason": item.get("truncation_reason"),
                "size_bytes": item.get("size_bytes", 0),
                "line_count": item.get("line_count", 0),
                "source_scope": item.get("source_scope", SOURCE_SCOPE_RUNTIME),
            }
        )

    return compact


def _source_file_path(item: dict[str, Any]) -> str | None:
    source = item.get("source")
    return source.get("file_path") if isinstance(source, dict) else None


def _build_workspace_units(
    repo_root: Path,
    *,
    file_inventory: dict[str, Any],
    package_graph: dict[str, Any],
    http_surface: dict[str, Any],
) -> list[dict[str, Any]]:
    files = file_inventory.get("files", [])
    units: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for module in _go_modules(package_graph):
        root_path = module.get("root_dir") or "."
        unit = _new_workspace_unit(
            root_path=root_path,
            unit_kind="backend",
            roles=["backend"],
            manifest_paths=[module.get("go_mod_path") or _join_path(root_path, "go.mod")],
            ownership_mode="prefix",
            languages=["go"],
            frameworks=["go"],
            name=module.get("path") or _unit_name_from_root(root_path),
        )
        unit["go"] = {
            "module_path": module.get("path"),
            "go_version": module.get("go_version"),
            "toolchain": module.get("toolchain"),
            "packages_total": 0,
            "entrypoints": [],
            "important_packages": [],
        }
        _add_unit(units, seen, unit)

    for package_json_path in _manifest_paths(files, "package.json"):
        root_path = _parent_dir(package_json_path)
        manifest = _read_package_json(repo_root / package_json_path)
        unit_files = _files_under_root(files, root_path)
        js_summary = _javascript_summary(
            root_path=root_path,
            manifest=manifest,
            files=unit_files,
            repo_root=repo_root,
        )
        unit_kind = "frontend" if js_summary["is_frontend"] else "shared"
        roles = ["frontend"] if unit_kind == "frontend" else ["shared"]
        unit = _new_workspace_unit(
            root_path=root_path,
            unit_kind=unit_kind,
            roles=roles,
            manifest_paths=[package_json_path],
            ownership_mode="prefix",
            languages=js_summary["languages"],
            frameworks=js_summary["frameworks"],
            name=js_summary["package_name"] or _unit_name_from_root(root_path),
        )
        unit["javascript"] = js_summary
        _add_unit(units, seen, unit)

    infra_files = [file_record["path"] for file_record in files if _is_infra_file(file_record["path"])]
    if infra_files:
        unit = _new_workspace_unit(
            root_path=".",
            unit_kind="infra",
            roles=["infra"],
            manifest_paths=infra_files[:_MAX_UNIT_KEY_FILES],
            ownership_mode="exact",
            exact_file_paths=infra_files,
            languages=[],
            frameworks=_infra_frameworks(infra_files),
            name="infra",
        )
        _add_unit(units, seen, unit)

    docs_files = [
        file_record["path"]
        for file_record in files
        if file_record["path"].startswith("docs/") or file_record.get("kind") == "api_spec"
    ]
    if docs_files:
        docs_root = "docs" if any(path.startswith("docs/") for path in docs_files) else "."
        unit = _new_workspace_unit(
            root_path=docs_root,
            unit_kind="docs",
            roles=["docs"],
            manifest_paths=[],
            ownership_mode="prefix" if docs_root == "docs" else "exact",
            exact_file_paths=docs_files if docs_root == "." else None,
            languages=["markdown"] if any(path.lower().endswith((".md", ".mdx", ".rst")) for path in docs_files) else [],
            frameworks=[],
            name="docs",
        )
        _add_unit(units, seen, unit)

    if not units:
        _add_unit(
            units,
            seen,
            _new_workspace_unit(
                root_path=".",
                unit_kind="shared",
                roles=["shared"],
                manifest_paths=[],
                ownership_mode="prefix",
                languages=_languages_for_files(files),
                frameworks=[],
                name="repository",
            ),
        )

    _assign_workspace_unit_files(units, files)
    _attach_go_packages_to_units(units, package_graph)
    _attach_http_surface_to_units(units, http_surface)

    for unit in units:
        unit.pop("_ownership_mode", None)
        unit.pop("_exact_file_paths", None)
        unit["roles"] = sorted(set(unit["roles"]))
        unit["languages"] = sorted(set(unit["languages"]))
        unit["frameworks"] = sorted(set(unit["frameworks"]))
        unit["manifest_paths"] = sorted(set(filter(None, unit["manifest_paths"])))
        unit["key_files"] = sorted(unit["key_files"], key=lambda item: item["path"])[:_MAX_UNIT_KEY_FILES]

    units.sort(key=lambda item: (item["root_path"] != ".", item["root_path"], item["unit_kind"]))
    return units


def _new_workspace_unit(
    *,
    root_path: str,
    unit_kind: str,
    roles: list[str],
    manifest_paths: list[str | None],
    ownership_mode: str,
    languages: list[str],
    frameworks: list[str],
    name: str,
    exact_file_paths: list[str] | None = None,
) -> dict[str, Any]:
    root_path = _normalize_root_path(root_path)
    return {
        "workspace_unit_id": _workspace_unit_id(unit_kind, root_path),
        "root_path": root_path,
        "name": name,
        "unit_kind": unit_kind,
        "roles": roles,
        "languages": languages,
        "frameworks": frameworks,
        "manifest_paths": [path for path in manifest_paths if path],
        "key_files": [],
        "file_counts": {
            "files_total": 0,
            "bytes_total": 0,
            "by_owner": {},
            "by_kind": {},
            "by_extension": {},
        },
        "_ownership_mode": ownership_mode,
        "_exact_file_paths": set(exact_file_paths or []),
    }


def _add_unit(units: list[dict[str, Any]], seen: set[tuple[str, str]], unit: dict[str, Any]) -> None:
    key = (unit["unit_kind"], unit["root_path"])
    if key in seen:
        return

    seen.add(key)
    units.append(unit)


def _assign_workspace_unit_files(units: list[dict[str, Any]], files: list[dict[str, Any]]) -> None:
    for file_record in files:
        unit = _unit_for_file(file_record["path"], units)
        if unit is None:
            continue

        owner = _file_owner(file_record)
        kind = file_record.get("kind", "other")
        extension = PurePosixPath(file_record["path"]).suffix.lower() or "<none>"
        unit["file_counts"]["files_total"] += 1
        unit["file_counts"]["bytes_total"] += file_record.get("size_bytes", 0)
        unit["file_counts"]["by_owner"] = _increment_count(unit["file_counts"]["by_owner"], owner)
        unit["file_counts"]["by_kind"] = _increment_count(unit["file_counts"]["by_kind"], kind)
        unit["file_counts"]["by_extension"] = _increment_count(unit["file_counts"]["by_extension"], extension)
        if _is_key_file(file_record["path"], kind):
            unit["key_files"].append(
                {
                    "path": file_record["path"],
                    "kind": kind,
                    "owner": owner,
                    "size_bytes": file_record.get("size_bytes", 0),
                    "line_count": file_record.get("line_count", 0),
                }
            )

    for unit in units:
        for count_key in ("by_owner", "by_kind", "by_extension"):
            unit["file_counts"][count_key] = dict(sorted(unit["file_counts"][count_key].items()))


def _unit_for_file(path: str, units: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates = []
    for unit in units:
        if unit["_ownership_mode"] == "exact":
            if path in unit["_exact_file_paths"]:
                candidates.append((1000, len(unit["root_path"]), unit))
            continue

        if _path_under_root(path, unit["root_path"]):
            priority = 900 if unit["unit_kind"] in {"docs", "infra"} else 500
            candidates.append((priority, len(unit["root_path"]), unit))

    if not candidates:
        return None

    candidates.sort(key=lambda item: (item[0], item[1], item[2]["workspace_unit_id"]), reverse=True)
    return candidates[0][2]


def _attach_go_packages_to_units(units: list[dict[str, Any]], package_graph: dict[str, Any]) -> None:
    lookup = _build_workspace_unit_lookup(units)
    packages_by_unit: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    entrypoints_by_unit: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for package in package_graph.get("packages", []):
        unit_id = _workspace_unit_id_for_path(package.get("dir_path", "."), lookup)
        if unit_id is not None:
            packages_by_unit[unit_id].append(package)

    for entrypoint in package_graph.get("entrypoints", []):
        unit_id = _workspace_unit_id_for_path(entrypoint.get("dir_path", "."), lookup)
        if unit_id is not None:
            entrypoints_by_unit[unit_id].append(entrypoint)

    for unit in units:
        if unit["unit_kind"] != "backend" or "go" not in unit:
            continue

        packages = packages_by_unit.get(unit["workspace_unit_id"], [])
        unit["go"]["packages_total"] = len(packages)
        unit["go"]["entrypoints"] = sorted(
            entrypoints_by_unit.get(unit["workspace_unit_id"], []),
            key=lambda item: (item["dir_path"], item["package_id"]),
        )
        unit["go"]["important_packages"] = [
            _compact_important_package(package, lookup) for package in _important_packages(packages)
        ]


def _attach_http_surface_to_units(units: list[dict[str, Any]], http_surface: dict[str, Any]) -> None:
    lookup = _build_workspace_unit_lookup(units)
    routes_by_unit: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for route in http_surface.get("routes", []):
        unit_id = _workspace_unit_id_for_path(route.get("file_path", "."), lookup)
        if unit_id is not None:
            routes_by_unit[unit_id].append(route)

    for unit in units:
        routes = routes_by_unit.get(unit["workspace_unit_id"], [])
        if routes:
            unit["http_surface"] = {
                "detected": True,
                "frameworks": sorted({route.get("framework") for route in routes if route.get("framework")}),
                "routes_total": len(routes),
            }
            unit["frameworks"].extend(unit["http_surface"]["frameworks"])


def _build_workspace_unit_lookup(units: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "units": [
            {
                "workspace_unit_id": unit["workspace_unit_id"],
                "root_path": unit["root_path"],
                "unit_kind": unit["unit_kind"],
            }
            for unit in units
            if unit["unit_kind"] not in {"infra", "docs"}
        ]
    }


def _workspace_unit_id_for_path(path: str, workspace_unit_lookup: dict[str, Any]) -> str | None:
    candidates = [
        unit
        for unit in workspace_unit_lookup.get("units", [])
        if _path_under_root(path, unit["root_path"])
    ]
    if not candidates:
        return None

    candidates.sort(key=lambda item: (len(item["root_path"]), item["workspace_unit_id"]), reverse=True)
    return candidates[0]["workspace_unit_id"]


def _manifest_paths(files: list[dict[str, Any]], name: str) -> list[str]:
    return sorted(file_record["path"] for file_record in files if PurePosixPath(file_record["path"]).name == name)


def _files_under_root(files: list[dict[str, Any]], root_path: str) -> list[dict[str, Any]]:
    return [file_record for file_record in files if _path_under_root(file_record["path"], root_path)]


def _read_package_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return {}

    return value if isinstance(value, dict) else {}


def _javascript_summary(
    *,
    root_path: str,
    manifest: dict[str, Any],
    files: list[dict[str, Any]],
    repo_root: Path,
) -> dict[str, Any]:
    dependencies = _package_dependencies(manifest)
    frameworks = _javascript_frameworks(dependencies, files)
    languages = _languages_for_files(files)
    package_manager = _package_manager_for_root(repo_root, root_path)
    scripts = _package_scripts(manifest)
    frontend_hints = _frontend_hints(root_path, files)
    is_frontend = bool(frameworks.intersection({"react", "vue", "next", "nuxt", "svelte", "angular", "vite"}))
    is_frontend = is_frontend or bool(frontend_hints["route_directories"] or frontend_hints["component_directories"])

    return {
        "package_name": manifest.get("name"),
        "package_manager": package_manager,
        "languages": sorted(languages or {"javascript"}),
        "frameworks": sorted(frameworks),
        "is_frontend": is_frontend,
        "scripts": scripts,
        "dependency_hints": _dependency_hints(dependencies),
        **frontend_hints,
    }


def _package_dependencies(manifest: dict[str, Any]) -> dict[str, str]:
    dependencies: dict[str, str] = {}
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        section_value = manifest.get(section)
        if isinstance(section_value, dict):
            dependencies.update({str(key): str(value) for key, value in section_value.items()})

    return dict(sorted(dependencies.items()))


def _javascript_frameworks(dependencies: dict[str, str], files: list[dict[str, Any]]) -> set[str]:
    names = set(dependencies)
    frameworks: set[str] = set()
    framework_map = {
        "@angular/core": "angular",
        "@sveltejs/kit": "svelte",
        "@vitejs/plugin-react": "vite",
        "next": "next",
        "nuxt": "nuxt",
        "react": "react",
        "svelte": "svelte",
        "vite": "vite",
        "vue": "vue",
    }
    for dependency, framework in framework_map.items():
        if dependency in names:
            frameworks.add(framework)

    paths = {file_record["path"].lower() for file_record in files}
    if any("/vite.config." in f"/{path}" for path in paths):
        frameworks.add("vite")
    if any("/next.config." in f"/{path}" for path in paths):
        frameworks.add("next")
    if any("/nuxt.config." in f"/{path}" for path in paths):
        frameworks.add("nuxt")
    if any("/svelte.config." in f"/{path}" for path in paths):
        frameworks.add("svelte")
    if any("/angular.json" in f"/{path}" for path in paths):
        frameworks.add("angular")

    return frameworks


def _package_manager_for_root(repo_root: Path, root_path: str) -> str | None:
    root = repo_root if root_path == "." else repo_root / root_path
    if (root / "pnpm-lock.yaml").exists() or (repo_root / "pnpm-workspace.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "package-lock.json").exists():
        return "npm"
    if (root / "bun.lockb").exists():
        return "bun"
    return None


def _package_scripts(manifest: dict[str, Any]) -> list[dict[str, str]]:
    scripts = manifest.get("scripts")
    if not isinstance(scripts, dict):
        return []

    preferred = ("dev", "start", "build", "test", "lint", "preview", "typecheck")
    items = [
        {"name": name, "command": str(scripts[name])}
        for name in preferred
        if name in scripts
    ]
    remaining = [
        {"name": str(name), "command": str(command)}
        for name, command in sorted(scripts.items())
        if name not in preferred
    ]
    return (items + remaining)[:10]


def _dependency_hints(dependencies: dict[str, str]) -> list[dict[str, str]]:
    return [
        {"name": name, "version": version}
        for name, version in sorted(dependencies.items())[:_MAX_DEPENDENCY_HINTS]
    ]


def _frontend_hints(root_path: str, files: list[dict[str, Any]]) -> dict[str, list[str]]:
    directories = {_parent_dir(file_record["path"]) for file_record in files}
    route_dirs = _matching_dirs(root_path, directories, {"app", "pages", "routes"})
    component_dirs = _matching_dirs(root_path, directories, {"components"})
    api_client_dirs = _matching_dirs(root_path, directories, {"api", "client", "clients"})
    generated_sdk_dirs = [
        directory
        for directory in sorted(directories)
        if any(part in {"generated", "sdk"} for part in PurePosixPath(directory).parts)
        and _path_under_root(directory, root_path)
    ]
    return {
        "route_directories": route_dirs[:_MAX_UNIT_KEY_FILES],
        "component_directories": component_dirs[:_MAX_UNIT_KEY_FILES],
        "api_client_directories": api_client_dirs[:_MAX_UNIT_KEY_FILES],
        "generated_sdk_directories": generated_sdk_dirs[:_MAX_UNIT_KEY_FILES],
    }


def _matching_dirs(root_path: str, directories: set[str], names: set[str]) -> list[str]:
    matched = []
    for directory in sorted(directories):
        if not _path_under_root(directory, root_path):
            continue

        parts = set(PurePosixPath(directory).parts)
        if parts.intersection(names):
            matched.append(directory)

    return matched


def _languages_for_files(files: list[dict[str, Any]]) -> list[str]:
    languages = set()
    for file_record in files:
        path = file_record["path"].lower()
        suffix = PurePosixPath(path).suffix
        if suffix == ".go":
            languages.add("go")
        elif suffix in {".ts", ".tsx"}:
            languages.add("typescript")
        elif suffix in {".js", ".jsx", ".mjs", ".cjs"}:
            languages.add("javascript")
        elif suffix in {".css", ".scss", ".sass", ".less"}:
            languages.add("css")
        elif suffix in {".html", ".vue", ".svelte"}:
            languages.add("markup")
        elif suffix in {".md", ".mdx", ".rst"}:
            languages.add("markdown")
        elif suffix in {".yaml", ".yml", ".json", ".toml", ".ini", ".env"}:
            languages.add("configuration")

    return sorted(languages)


def _is_infra_file(path: str) -> bool:
    pure_path = PurePosixPath(path)
    lower_name = pure_path.name.lower()
    lower_parts = {part.lower() for part in pure_path.parts}
    return (
        lower_name == "dockerfile"
        or lower_name.startswith("dockerfile.")
        or lower_name.startswith("docker-compose")
        or lower_name in {"compose.yaml", "compose.yml", "makefile"}
        or bool(lower_parts.intersection({".github", "deploy", "deployment", "k8s", "kubernetes", "terraform"}))
    )


def _infra_frameworks(paths: list[str]) -> list[str]:
    frameworks = set()
    for path in paths:
        lower_name = PurePosixPath(path).name.lower()
        lower_parts = {part.lower() for part in PurePosixPath(path).parts}
        if "docker" in lower_name or lower_name.startswith("compose"):
            frameworks.add("docker")
        if lower_name == "makefile":
            frameworks.add("make")
        if lower_parts.intersection({"k8s", "kubernetes"}):
            frameworks.add("kubernetes")
        if "terraform" in lower_parts:
            frameworks.add("terraform")
        if ".github" in lower_parts:
            frameworks.add("github_actions")

    return sorted(frameworks)


def _file_owner(file_record: dict[str, Any]) -> str:
    path = file_record["path"]
    kind = file_record.get("kind")
    source_scope = source_scope_from_record(file_record)
    if source_scope == "vendor":
        return "vendor"
    if source_scope == "generated":
        return "generated"
    if source_scope == "test":
        return "test"
    if source_scope == "infra" or _is_infra_file(path):
        return "infra"
    if source_scope == "docs" or path.startswith("docs/") or kind == "markdown":
        return "docs"
    if path.endswith(".go"):
        return "backend"
    if PurePosixPath(path).suffix.lower() in {
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".html",
        ".vue",
        ".svelte",
    }:
        return "frontend"
    return "shared"


def _increment_count(counter: dict[str, int], key: str) -> dict[str, int]:
    counter[key] = counter.get(key, 0) + 1
    return counter


def _workspace_unit_id(unit_kind: str, root_path: str) -> str:
    normalized_root = "root" if root_path == "." else root_path.strip("/").replace("/", "-")
    return f"{unit_kind}:{normalized_root}"


def _normalize_root_path(root_path: str) -> str:
    normalized = root_path.strip("/")
    return normalized or "."


def _path_under_root(path: str, root_path: str) -> bool:
    root_path = _normalize_root_path(root_path)
    if root_path == ".":
        return True

    return path == root_path or path.startswith(f"{root_path}/")


def _parent_dir(path: str) -> str:
    parent = PurePosixPath(path).parent.as_posix()
    return "." if parent == "." else parent


def _join_path(root_path: str, name: str) -> str:
    return name if root_path == "." else f"{root_path}/{name}"


def _unit_name_from_root(root_path: str) -> str:
    return "repository" if root_path == "." else PurePosixPath(root_path).name


def _attach_budget_metadata(
    document: dict[str, Any],
    *,
    file_inventory: dict[str, Any],
    go_symbols: dict[str, Any],
    package_graph: dict[str, Any],
    config_inventory: dict[str, Any],
) -> None:
    source_config_keys = sum(len(item.get("keys", [])) for item in config_inventory.get("config_files", []))
    important_packages_total = len(document["go"]["important_packages"])
    important_symbols_total = len(document["code_outline"]["important_symbols"])
    omitted_sections = [
        {
            "source": "file_inventory.files",
            "items_total": len(file_inventory.get("files", [])),
            "reason": "project_model_v2_keeps_layout_counts_and_key_files_only",
        },
        {
            "source": "package_graph.packages",
            "items_total": len(package_graph.get("packages", [])),
            "items_included": important_packages_total,
            "reason": "project_model_v2_keeps_important_packages_only",
        },
        {
            "source": "package_graph.edges",
            "items_total": len(package_graph.get("edges", [])),
            "reason": "project_model_v2_keeps_dependency_summary_only",
        },
        {
            "source": "go_symbols.symbols",
            "items_total": go_symbols.get("summary", {}).get("symbols_total", len(go_symbols.get("symbols", []))),
            "items_included": important_symbols_total,
            "reason": "project_model_v2_keeps_important_symbols_only",
        },
        {
            "source": "config_inventory.config_files.keys",
            "items_total": source_config_keys,
            "reason": "project_model_v2_keeps_config_file_key_counts_only",
        },
    ]
    truncation_reasons = [
        item["reason"]
        for item in omitted_sections
        if item.get("items_total", 0) > item.get("items_included", 0)
    ]
    document["budget"] = {
        "estimated_document_bytes": 0,
        "estimated_document_tokens": 0,
        "estimation": "rough_bytes_div_4",
        "limits": {
            "max_important_packages": _MAX_IMPORTANT_PACKAGES,
            "max_important_symbols": _MAX_IMPORTANT_SYMBOLS,
            "max_config_items_per_section": _MAX_CONFIG_ITEMS,
            "max_key_files": _MAX_KEY_FILES,
            "max_workspace_unit_key_files": _MAX_UNIT_KEY_FILES,
        },
        "omitted_sections": omitted_sections,
        "truncation_reasons": sorted(set(truncation_reasons)),
    }
    for _ in range(3):
        payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
        estimated_bytes = len(payload)
        estimated_tokens = max(1, estimated_bytes // 4)
        if (
            document["budget"]["estimated_document_bytes"] == estimated_bytes
            and document["budget"]["estimated_document_tokens"] == estimated_tokens
        ):
            break

        document["budget"]["estimated_document_bytes"] = estimated_bytes
        document["budget"]["estimated_document_tokens"] = estimated_tokens


def _detect_external_integrations(
    package_graph: dict[str, Any],
    config_inventory: dict[str, Any],
) -> list[dict[str, Any]]:
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in package_graph.get("edges", []):
        if not edge.get("runtime_scope", True):
            continue

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
        if env_var.get("source_scope", SOURCE_SCOPE_RUNTIME) != SOURCE_SCOPE_RUNTIME:
            continue

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


def _detect_http_surface(
    repo_root: Path,
    package_graph: dict[str, Any],
    go_symbols: dict[str, Any],
) -> dict[str, Any]:
    http_imports: dict[str, set[str]] = defaultdict(set)
    http_file_scopes: dict[str, str] = {}
    file_packages = _build_file_package_lookup(package_graph)
    symbol_lookup = _build_symbol_lookup(go_symbols)

    for edge in package_graph.get("edges", []):
        framework = _HTTP_IMPORTS.get(edge.get("import_path"))
        if framework is None:
            continue

        for file_ref in edge.get("file_source_scopes", []):
            source_scope = file_ref.get("source_scope", SOURCE_SCOPE_RUNTIME)
            if source_scope != SOURCE_SCOPE_RUNTIME:
                continue

            file_path = file_ref.get("path")
            if not file_path:
                continue

            http_imports[file_path].add(framework)
            http_file_scopes[file_path] = source_scope

    routes: list[dict[str, Any]] = []
    unsupported_patterns: list[dict[str, Any]] = []
    for file_path, frameworks in sorted(http_imports.items()):
        source_path = repo_root / file_path
        if not source_path.exists():
            continue

        lines = source_path.read_text(encoding="utf-8", errors="replace").splitlines()
        package_ref = _primary_file_package(file_packages.get(file_path, []))
        extracted = _extract_http_routes_from_file(
            file_path=file_path,
            lines=lines,
            frameworks=sorted(frameworks),
            package_ref=package_ref,
            symbol_lookup=symbol_lookup,
            source_scope=http_file_scopes.get(file_path, SOURCE_SCOPE_RUNTIME),
        )
        routes.extend(extracted["routes"])
        unsupported_patterns.extend(extracted["unsupported_patterns"])

    routes = _dedupe_routes(routes)
    routes.sort(key=lambda item: (item["file_path"], item["line"], item["method"] or "", item["path"]))
    unsupported_patterns.sort(
        key=lambda item: (item["file_path"], item["line"], item["kind"], item["expression"])
    )
    frameworks = sorted({framework for values in http_imports.values() for framework in values})
    detected = bool(routes) or any(framework != "net_http" for framework in frameworks)
    confidence = "high" if routes else "medium" if detected or unsupported_patterns else "none"

    return {
        "detected": detected,
        "confidence": confidence,
        "frameworks": frameworks,
        "routes": routes,
        "unsupported_patterns": unsupported_patterns,
    }


def _extract_http_routes_from_file(
    file_path: str,
    lines: list[str],
    frameworks: list[str],
    package_ref: dict[str, Any] | None,
    symbol_lookup: dict[str, Any],
    source_scope: str,
) -> dict[str, list[dict[str, Any]]]:
    routes: list[dict[str, Any]] = []
    unsupported_patterns: list[dict[str, Any]] = []
    receiver_prefixes: dict[str, str] = {}

    for statement in _iter_http_call_statements(lines):
        _update_receiver_prefixes(receiver_prefixes, statement["text"])
        statement_prefixes = _route_block_prefixes(receiver_prefixes, statement["text"])
        route_context = {
            "file_path": file_path,
            "frameworks": frameworks,
            "package": package_ref,
            "symbol_lookup": symbol_lookup,
            "receiver_prefixes": {**receiver_prefixes, **statement_prefixes},
            "source_scope": source_scope,
        }

        routes.extend(_extract_method_routes(statement, route_context))
        routes.extend(_extract_method_func_routes(statement, route_context))
        routes.extend(_extract_handle_routes(statement, route_context))
        unsupported_patterns.extend(_extract_unsupported_http_patterns(statement, route_context))

    return {"routes": routes, "unsupported_patterns": unsupported_patterns}


def _iter_http_call_statements(lines: list[str]) -> list[dict[str, Any]]:
    statements: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not _looks_like_http_statement(line):
            index += 1
            continue

        start_line = index + 1
        chunks = [line]
        paren_balance = _paren_delta(line)
        brace_balance = _brace_delta(line)
        index += 1
        while index < len(lines):
            previous = chunks[-1].strip()
            next_line = lines[index]
            next_stripped = next_line.strip()
            should_continue = (
                paren_balance > 0
                or brace_balance > 0
                or previous.endswith(".")
                or next_stripped.startswith(".")
            )
            if not should_continue:
                break

            chunks.append(next_line)
            paren_balance += _paren_delta(next_line)
            brace_balance += _brace_delta(next_line)
            index += 1

        statements.append({"line": start_line, "text": "\n".join(chunks)})

    return statements


def _looks_like_http_statement(line: str) -> bool:
    return any(
        token in line
        for token in (
            ".GET",
            ".POST",
            ".PUT",
            ".DELETE",
            ".PATCH",
            ".HEAD",
            ".OPTIONS",
            ".Get",
            ".Post",
            ".Put",
            ".Delete",
            ".Patch",
            ".Head",
            ".Options",
            ".Method",
            ".MethodFunc",
            ".Handle",
            ".HandleFunc",
            ".Methods",
            ".Group",
            ".Route",
            ".PathPrefix",
            "http.Handle",
        )
    )


def _update_receiver_prefixes(receiver_prefixes: dict[str, str], statement: str) -> None:
    for match in _HTTP_GROUP_ASSIGN_RE.finditer(statement):
        args = _extract_call_args(statement, match.end() - 1)
        prefix = _literal_arg(args[0]) if args else None
        if prefix is None:
            continue

        base_prefix = receiver_prefixes.get(match.group("base"))
        receiver_prefixes[match.group("target")] = _join_route_paths(base_prefix, prefix)


def _route_block_prefixes(receiver_prefixes: dict[str, str], statement: str) -> dict[str, str]:
    prefixes: dict[str, str] = {}
    for match in _HTTP_ROUTE_BLOCK_RE.finditer(statement):
        base_prefix = receiver_prefixes.get(match.group("base"))
        prefixes[match.group("target")] = _join_route_paths(base_prefix, match.group("prefix"))

    return prefixes


def _extract_method_routes(statement: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    text = statement["text"]
    for match in _HTTP_ROUTE_METHOD_RE.finditer(text):
        args = _extract_call_args(text, match.end() - 1)
        path = _literal_arg(args[0]) if args else None
        if path is None:
            continue

        method = match.group("method").upper()
        if method not in _HTTP_METHODS:
            continue

        receiver = match.group("receiver")
        handler_expression = args[1] if len(args) > 1 else None
        routes.append(
            _route_record(
                context,
                line=statement["line"] + text[: match.start()].count("\n"),
                receiver=receiver,
                method=method,
                path=path,
                framework=_framework_for_method_call(match.group("method"), context["frameworks"]),
                handler_expression=handler_expression,
            )
        )

    return routes


def _extract_method_func_routes(statement: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    text = statement["text"]
    for match in _HTTP_METHOD_FUNC_RE.finditer(text):
        args = _extract_call_args(text, match.end() - 1)
        method = _literal_arg(args[0]).upper() if args and _literal_arg(args[0]) else None
        path = _literal_arg(args[1]) if len(args) > 1 else None
        if method not in _HTTP_METHODS or path is None:
            continue

        receiver = match.group("receiver")
        handler_expression = args[2] if len(args) > 2 else None
        routes.append(
            _route_record(
                context,
                line=statement["line"] + text[: match.start()].count("\n"),
                receiver=receiver,
                method=method,
                path=path,
                framework=_framework_for_method_func_call(context["frameworks"]),
                handler_expression=handler_expression,
            )
        )

    return routes


def _extract_handle_routes(statement: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
    routes: list[dict[str, Any]] = []
    text = statement["text"]
    for match in _HTTP_HANDLE_RE.finditer(text):
        args = _extract_call_args(text, match.end() - 1)
        path = _literal_arg(args[0]) if args else None
        if path is None:
            continue

        receiver = match.group("receiver")
        handler_expression = args[1] if len(args) > 1 else None
        methods = _method_chain_methods(text[match.end() :])
        framework = "net_http" if receiver == "http" else _framework_for_handle_call(
            context["frameworks"],
            has_methods=bool(methods),
        )
        for method in methods or [None]:
            routes.append(
                _route_record(
                    context,
                    line=statement["line"] + text[: match.start()].count("\n"),
                    receiver=receiver,
                    method=method,
                    path=path,
                    framework=framework,
                    handler_expression=handler_expression,
                )
            )

    return routes


def _extract_unsupported_http_patterns(
    statement: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    unsupported: list[dict[str, Any]] = []
    text = statement["text"]
    for match in list(_HTTP_ROUTE_METHOD_RE.finditer(text)) + list(_HTTP_HANDLE_RE.finditer(text)):
        args = _extract_call_args(text, match.end() - 1)
        if not args or _literal_arg(args[0]) is not None:
            continue

        unsupported.append(
            {
                "kind": "dynamic_route_path",
                "framework": _preferred_framework(context["frameworks"]),
                "file_path": context["file_path"],
                "line": statement["line"] + text[: match.start()].count("\n"),
                "expression": _compact_expression(args[0]),
                "reason": "route path is not a string literal",
                "source_scope": context["source_scope"],
                "runtime_scope": runtime_scope_from_source_scope(context["source_scope"]),
            }
        )

    for match in _HTTP_GROUP_ASSIGN_RE.finditer(text):
        args = _extract_call_args(text, match.end() - 1)
        if not args or _literal_arg(args[0]) is not None:
            continue

        unsupported.append(
            {
                "kind": "dynamic_route_group",
                "framework": _preferred_framework(context["frameworks"]),
                "file_path": context["file_path"],
                "line": statement["line"] + text[: match.start()].count("\n"),
                "expression": _compact_expression(args[0]),
                "reason": "route group prefix is not a string literal",
                "source_scope": context["source_scope"],
                "runtime_scope": runtime_scope_from_source_scope(context["source_scope"]),
            }
        )

    return unsupported


def _route_record(
    context: dict[str, Any],
    *,
    line: int,
    receiver: str,
    method: str | None,
    path: str,
    framework: str | None,
    handler_expression: str | None,
) -> dict[str, Any]:
    package_ref = context["package"]
    handler = _resolve_handler(handler_expression, package_ref, context["symbol_lookup"])
    return {
        "method": method,
        "path": _join_route_paths(context["receiver_prefixes"].get(receiver), path),
        "framework": framework,
        "file_path": context["file_path"],
        "line": line,
        "package": package_ref,
        "handler": handler,
        "confidence": "high" if _literal_text(path) else "medium",
        "source_scope": context["source_scope"],
        "runtime_scope": runtime_scope_from_source_scope(context["source_scope"]),
    }


def _extract_call_args(text: str, open_paren_index: int) -> list[str]:
    if open_paren_index < 0 or open_paren_index >= len(text) or text[open_paren_index] != "(":
        return []

    args: list[str] = []
    current: list[str] = []
    depth = 0
    quote: str | None = None
    index = open_paren_index + 1
    while index < len(text):
        char = text[index]
        if quote is not None:
            current.append(char)
            if char == quote and (quote == "`" or text[index - 1] != "\\"):
                quote = None
            index += 1
            continue

        if char in {'"', "`"}:
            quote = char
            current.append(char)
        elif char in "([{":
            depth += 1
            current.append(char)
        elif char in ")]}":
            if depth == 0 and char == ")":
                value = "".join(current).strip()
                if value:
                    args.append(value)
                return args
            depth = max(0, depth - 1)
            current.append(char)
        elif char == "," and depth == 0:
            args.append("".join(current).strip())
            current = []
        else:
            current.append(char)
        index += 1

    return args


def _literal_arg(value: str | None) -> str | None:
    if value is None:
        return None

    match = _HTTP_LITERAL_RE.match(value)
    return match.group("value") if match else None


def _literal_text(value: str | None) -> bool:
    return value is not None and value != ""


def _method_chain_methods(text: str) -> list[str]:
    match = _HTTP_METHODS_CHAIN_RE.search(text)
    if match is None:
        return []

    methods = []
    for arg in _split_args(match.group("args")):
        method = _literal_arg(arg)
        if method is not None and method.upper() in _HTTP_METHODS:
            methods.append(method.upper())

    return sorted(set(methods))


def _split_args(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _resolve_handler(
    handler_expression: str | None,
    package_ref: dict[str, Any] | None,
    symbol_lookup: dict[str, Any],
) -> dict[str, Any] | None:
    expression = _normalize_handler_expression(handler_expression)
    if expression is None:
        return None

    symbol = None
    if package_ref is not None:
        package_name = package_ref.get("name")
        symbol = symbol_lookup["by_package_and_name"].get((package_name, expression))

    if symbol is None:
        symbol = symbol_lookup["by_qualified_name"].get(expression)

    if symbol is None and "." in expression:
        receiver, name = expression.rsplit(".", 1)
        symbol = symbol_lookup["by_package_and_name"].get((receiver, name))

    if symbol is None:
        return {"expression": expression, "symbol": None}

    return {
        "expression": expression,
        "symbol": {
            "symbol_id": symbol["symbol_id"],
            "qualified_name": symbol["qualified_name"],
            "kind": symbol["kind"],
            "file_path": symbol["file_path"],
            "start_line": symbol["start_line"],
            "end_line": symbol["end_line"],
        },
    }


def _normalize_handler_expression(value: str | None) -> str | None:
    if value is None:
        return None

    expression = _compact_expression(value).removeprefix("&")
    if not expression or expression.startswith("func(") or expression.startswith("func "):
        return expression or None

    return expression


def _compact_expression(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def _build_file_package_lookup(package_graph: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    lookup: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for package in package_graph.get("packages", []):
        ref = {
            "package_id": package["package_id"],
            "name": package["name"],
            "dir_path": package["dir_path"],
            "import_path": package.get("import_path"),
            "source_scope": package.get("source_scope", SOURCE_SCOPE_RUNTIME),
            "runtime_scope": package.get("runtime_scope", True),
        }
        for file_path in package.get("files", []):
            lookup[file_path].append(ref)

    for refs in lookup.values():
        refs.sort(key=lambda item: (not item.get("runtime_scope", True), item["name"].endswith("_test"), item["package_id"]))

    return lookup


def _primary_file_package(packages: list[dict[str, Any]]) -> dict[str, Any] | None:
    return packages[0] if packages else None


def _build_symbol_lookup(go_symbols: dict[str, Any]) -> dict[str, Any]:
    by_qualified_name: dict[str, dict[str, Any]] = {}
    by_package_and_name: dict[tuple[str | None, str], dict[str, Any]] = {}
    for symbol in go_symbols.get("symbols", []):
        by_qualified_name[symbol["qualified_name"]] = symbol
        by_package_and_name[(symbol.get("package"), symbol["name"])] = symbol

    return {
        "by_qualified_name": by_qualified_name,
        "by_package_and_name": by_package_and_name,
    }


def _dedupe_routes(routes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for route in routes:
        key = (
            route["file_path"],
            route["line"],
            route["method"],
            route["path"],
            route["handler"]["expression"] if route.get("handler") else None,
        )
        deduped[key] = route

    return list(deduped.values())


def _join_route_paths(prefix: str | None, path: str) -> str:
    if prefix is None or prefix in {"", "/"}:
        return path or "/"

    if path in {"", "/"}:
        return prefix

    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"


def _framework_for_method_call(method_name: str, frameworks: list[str]) -> str | None:
    if method_name.isupper():
        for framework in ("gin", "echo", "fiber"):
            if framework in frameworks:
                return framework

    for framework in ("chi", "fiber", "gin", "echo"):
        if framework in frameworks:
            return framework

    return _preferred_framework(frameworks)


def _framework_for_handle_call(frameworks: list[str], *, has_methods: bool) -> str | None:
    if has_methods and "gorilla_mux" in frameworks:
        return "gorilla_mux"

    for framework in ("chi", "gorilla_mux", "net_http"):
        if framework in frameworks:
            return framework

    return _preferred_framework(frameworks)


def _framework_for_method_func_call(frameworks: list[str]) -> str | None:
    for framework in ("chi", "gorilla_mux"):
        if framework in frameworks:
            return framework

    return _preferred_framework(frameworks)


def _paren_delta(line: str) -> int:
    return _char_delta(line, "(", ")")


def _brace_delta(line: str) -> int:
    return _char_delta(line, "{", "}")


def _char_delta(line: str, open_char: str, close_char: str) -> int:
    delta = 0
    quote: str | None = None
    for index, char in enumerate(line):
        if quote is not None:
            if char == quote and (quote == "`" or line[index - 1] != "\\"):
                quote = None
            continue

        if char in {'"', "`"}:
            quote = char
        elif char == open_char:
            delta += 1
        elif char == close_char:
            delta -= 1

    return delta


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
