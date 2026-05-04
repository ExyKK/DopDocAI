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
    package_model = _build_package_model(package_graph)
    symbol_model = _build_symbol_model(go_symbols)
    configuration_model = _build_configuration_model(config_inventory)
    external_integrations = _detect_external_integrations(package_graph, config_inventory)
    http_surface = _detect_http_surface(repo_root, package_graph, go_symbols)

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
        "api_specs": config_inventory.get("api_specs", []),
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


def _detect_http_surface(
    repo_root: Path,
    package_graph: dict[str, Any],
    go_symbols: dict[str, Any],
) -> dict[str, Any]:
    http_imports: dict[str, set[str]] = defaultdict(set)
    file_packages = _build_file_package_lookup(package_graph)
    symbol_lookup = _build_symbol_lookup(go_symbols)

    for package in package_graph.get("packages", []):
        for import_path in package.get("standard_library_imports", []) + package.get("external_imports", []):
            framework = _HTTP_IMPORTS.get(import_path)
            if framework is not None:
                for file_path in package.get("files", []):
                    http_imports[file_path].add(framework)

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
        }
        for file_path in package.get("files", []):
            lookup[file_path].append(ref)

    for refs in lookup.values():
        refs.sort(key=lambda item: (item["name"].endswith("_test"), item["package_id"]))

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
