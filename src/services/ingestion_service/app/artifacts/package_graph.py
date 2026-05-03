import hashlib
import json
import posixpath
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from git import Repo

from app.artifacts.models import BuiltAnalysisArtifact, analysis_artifact_storage_key
from app.worker.snapshot_resolver import list_head_tree_files

PACKAGE_GRAPH_ARTIFACT_KIND = "package_graph"
PACKAGE_GRAPH_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class GoModuleMetadata:
    root_dir: str
    path: str | None
    go_version: str | None
    toolchain: str | None
    go_mod_path: str | None


def build_package_graph_artifact(
    repo_path: str | Path,
    repository_id: str,
    snapshot_id: str,
    snapshot_metadata: dict[str, Any],
    go_symbols_artifact: BuiltAnalysisArtifact | dict[str, Any],
) -> BuiltAnalysisArtifact:
    repo_root = Path(repo_path)
    go_symbols = _load_go_symbols_document(go_symbols_artifact)
    modules = _read_go_modules(repo_root)
    package_modules = modules or (
        GoModuleMetadata(root_dir=".", path=None, go_version=None, toolchain=None, go_mod_path=None),
    )
    root_module = _root_module_or_empty(modules)

    package_builders = _group_go_files_by_package(go_symbols.get("files", []), package_modules)
    packages = _build_packages(package_builders)
    package_lookup = _build_package_lookup(packages)
    edges = _build_edges(package_builders, packages, package_lookup, package_modules)
    entrypoints = [
        {
            "package_id": package["package_id"],
            "dir_path": package["dir_path"],
            "import_path": package["import_path"],
            "name": package["name"],
            "entrypoint_kind": package["entrypoint_kind"],
            "files": package["files"],
        }
        for package in packages
        if package["is_entrypoint"]
    ]

    edge_kind_counts = Counter(edge["kind"] for edge in edges)
    summary = {
        "go_files_total": go_symbols.get("summary", {}).get(
            "go_files_total",
            snapshot_metadata["go_files_total"],
        ),
        "packages_total": len(packages),
        "entrypoint_packages_total": len(entrypoints),
        "edges_total": len(edges),
        "internal_edges_total": edge_kind_counts.get("internal", 0),
        "standard_library_edges_total": edge_kind_counts.get("standard_library", 0),
        "external_edges_total": edge_kind_counts.get("external", 0),
        "vendor_edges_total": edge_kind_counts.get("vendor", 0),
        "cgo_edges_total": edge_kind_counts.get("cgo", 0),
        "files_without_package_total": len(go_symbols.get("files", [])) - sum(
            len(builder["files"]) for builder in package_builders.values()
        ),
        "edge_kind_counts": dict(sorted(edge_kind_counts.items())),
    }

    document = {
        "artifact_kind": PACKAGE_GRAPH_ARTIFACT_KIND,
        "schema_version": PACKAGE_GRAPH_SCHEMA_VERSION,
        "snapshot": {
            "branch_name": snapshot_metadata["branch_name"],
            "commit_sha": snapshot_metadata["commit_sha"],
            "tree_hash": snapshot_metadata["tree_hash"],
        },
        "module": {
            "path": root_module.path,
            "go_version": root_module.go_version,
            "toolchain": root_module.toolchain,
            "go_mod_path": root_module.go_mod_path,
        },
        "modules": [_module_document(module) for module in modules],
        "summary": summary,
        "packages": packages,
        "edges": edges,
        "entrypoints": entrypoints,
    }

    payload = (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    checksum_sha256 = hashlib.sha256(payload).hexdigest()

    return BuiltAnalysisArtifact(
        artifact_kind=PACKAGE_GRAPH_ARTIFACT_KIND,
        schema_version=PACKAGE_GRAPH_SCHEMA_VERSION,
        format="json",
        content_type="application/json",
        storage_key=analysis_artifact_storage_key(
            repository_id=repository_id,
            snapshot_id=snapshot_id,
            artifact_kind=PACKAGE_GRAPH_ARTIFACT_KIND,
            schema_version=PACKAGE_GRAPH_SCHEMA_VERSION,
        ),
        checksum_sha256=checksum_sha256,
        size_bytes=len(payload),
        row_count=len(packages),
        payload=payload,
        summary=summary,
    )


def _load_go_symbols_document(go_symbols_artifact: BuiltAnalysisArtifact | dict[str, Any]) -> dict[str, Any]:
    if isinstance(go_symbols_artifact, BuiltAnalysisArtifact):
        return json.loads(go_symbols_artifact.payload.decode("utf-8"))

    return go_symbols_artifact


def _group_go_files_by_package(
    files: list[dict[str, Any]],
    modules: tuple[GoModuleMetadata, ...],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    builders: dict[tuple[str, str, str], dict[str, Any]] = {}

    for file_record in files:
        package_name = file_record.get("package")
        if not package_name:
            continue

        path = _normalize_path(file_record["path"])
        dir_path = _dir_path(path)
        module = _module_for_dir(dir_path, modules)
        key = (module.root_dir, dir_path, package_name)
        builder = builders.setdefault(
            key,
            {
                "module": module,
                "dir_path": dir_path,
                "name": package_name,
                "files": [],
                "imports": [],
            },
        )
        builder["files"].append(
            {
                "path": path,
                "symbols_total": file_record.get("symbols_total", 0),
                "is_generated": bool(file_record.get("is_generated")),
                "is_test": bool(file_record.get("is_test")),
                "is_vendor": bool(file_record.get("is_vendor")),
                "parse_error": bool(file_record.get("parse_error")),
            }
        )

        for import_record in file_record.get("imports", []):
            import_path = import_record.get("path")
            if not import_path:
                continue

            builder["imports"].append(
                {
                    "path": import_path,
                    "name": import_record.get("name"),
                    "is_dot": bool(import_record.get("is_dot")),
                    "is_blank": bool(import_record.get("is_blank")),
                    "file_path": path,
                }
            )

    return builders


def _build_packages(
    package_builders: dict[tuple[str, str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    packages: list[dict[str, Any]] = []

    for (_, dir_path, package_name), builder in sorted(package_builders.items()):
        module = builder["module"]
        files = sorted(builder["files"], key=lambda item: item["path"])
        import_path = _package_import_path(dir_path, module)
        entrypoint_kind = _entrypoint_kind(dir_path, package_name, module)
        package = {
            "package_id": _package_id(import_path, dir_path, package_name),
            "name": package_name,
            "module_id": _module_id(module),
            "module_root": module.root_dir,
            "module_path": module.path,
            "dir_path": dir_path,
            "import_path": import_path,
            "files": [file_record["path"] for file_record in files],
            "files_total": len(files),
            "symbols_total": sum(file_record["symbols_total"] for file_record in files),
            "imports": [],
            "internal_imports": [],
            "standard_library_imports": [],
            "external_imports": [],
            "vendor_imports": [],
            "cgo_imports": [],
            "is_command": package_name == "main",
            "is_entrypoint": entrypoint_kind is not None,
            "entrypoint_kind": entrypoint_kind,
            "is_test_package": package_name.endswith("_test") or all(file_record["is_test"] for file_record in files),
            "has_test_files": any(file_record["is_test"] for file_record in files),
            "has_generated_files": any(file_record["is_generated"] for file_record in files),
            "has_parse_errors": any(file_record["parse_error"] for file_record in files),
            "is_vendor": any(file_record["is_vendor"] for file_record in files) or _is_vendor_dir(dir_path),
        }
        packages.append(package)

    return packages


def _build_package_lookup(packages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_dir: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    internal_by_import_path: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    vendor_by_import_path: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    for package in packages:
        by_dir[package["dir_path"]].append(package)

        import_path = package["import_path"]
        if not import_path:
            continue

        if package["is_vendor"]:
            vendor_by_import_path[import_path].append(package)
        else:
            internal_by_import_path[import_path].append(package)

    return {
        "by_dir": {key: _primary_package(value) for key, value in by_dir.items()},
        "internal_by_import_path": {
            key: _primary_package(value) for key, value in internal_by_import_path.items()
        },
        "vendor_by_import_path": {
            key: _primary_package(value) for key, value in vendor_by_import_path.items()
        },
    }


def _build_edges(
    package_builders: dict[tuple[str, str, str], dict[str, Any]],
    packages: list[dict[str, Any]],
    package_lookup: dict[str, dict[str, Any]],
    modules: tuple[GoModuleMetadata, ...],
) -> list[dict[str, Any]]:
    packages_by_key = {
        (package["module_root"], package["dir_path"], package["name"]): package
        for package in packages
    }
    imports_by_package: dict[str, dict[str, list[dict[str, Any]]]] = {}
    edges: list[dict[str, Any]] = []

    for key, builder in sorted(package_builders.items()):
        package = packages_by_key[key]
        grouped_imports: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
        for import_record in builder["imports"]:
            grouped_imports[import_record["path"]].append(import_record)

        package_imports_by_kind: defaultdict[str, list[str]] = defaultdict(list)
        for import_path, import_records in sorted(grouped_imports.items()):
            target = _resolve_import(
                import_path,
                from_dir_path=package["dir_path"],
                modules=modules,
                package_lookup=package_lookup,
            )
            edge = {
                "from_package_id": package["package_id"],
                "from_import_path": package["import_path"],
                "from_dir_path": package["dir_path"],
                "import_path": import_path,
                "kind": target["kind"],
                "to_package_id": target["to_package_id"],
                "to_import_path": target["to_import_path"],
                "to_dir_path": target["to_dir_path"],
                "files": sorted({record["file_path"] for record in import_records}),
                "import_count": len(import_records),
                "import_names": sorted(
                    {record["name"] for record in import_records if record.get("name") is not None}
                ),
                "has_blank_import": any(record["is_blank"] for record in import_records),
                "has_dot_import": any(record["is_dot"] for record in import_records),
            }
            edges.append(edge)
            package_imports_by_kind[target["kind"]].append(import_path)

        imports_by_package[package["package_id"]] = package_imports_by_kind

    edges.sort(
        key=lambda item: (
            item["from_package_id"],
            item["kind"],
            item["import_path"],
        )
    )

    for package in packages:
        imports_by_kind = imports_by_package.get(package["package_id"], {})
        all_imports = sorted(
            {
                import_path
                for kind_imports in imports_by_kind.values()
                for import_path in kind_imports
            }
        )
        package["imports"] = all_imports
        package["internal_imports"] = sorted(imports_by_kind.get("internal", []))
        package["standard_library_imports"] = sorted(imports_by_kind.get("standard_library", []))
        package["external_imports"] = sorted(imports_by_kind.get("external", []))
        package["vendor_imports"] = sorted(imports_by_kind.get("vendor", []))
        package["cgo_imports"] = sorted(imports_by_kind.get("cgo", []))

    return edges


def _resolve_import(
    import_path: str,
    *,
    from_dir_path: str,
    modules: tuple[GoModuleMetadata, ...],
    package_lookup: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if import_path == "C":
        return _target("cgo", None, "C", None)

    if import_path.startswith("./") or import_path.startswith("../"):
        target_dir = _resolve_relative_dir(from_dir_path, import_path)
        target_package = package_lookup["by_dir"].get(target_dir) if target_dir is not None else None
        return _target("internal", target_package, target_package.get("import_path") if target_package else None, target_dir)

    target_package = package_lookup["internal_by_import_path"].get(import_path)
    if target_package is not None:
        return _target("internal", target_package, import_path, target_package["dir_path"])

    local_module = _module_for_import_path(import_path, modules)
    if local_module is not None:
        target_dir = _module_relative_dir(local_module, import_path)
        target_package = package_lookup["by_dir"].get(target_dir)
        return _target("internal", target_package, import_path, target_dir)

    vendor_package = package_lookup["vendor_by_import_path"].get(import_path)
    if vendor_package is not None:
        return _target("vendor", vendor_package, import_path, vendor_package["dir_path"])

    if _looks_like_standard_library(import_path):
        return _target("standard_library", None, import_path, None)

    return _target("external", None, import_path, None)


def _target(
    kind: str,
    package: dict[str, Any] | None,
    import_path: str | None,
    dir_path: str | None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "to_package_id": package["package_id"] if package else None,
        "to_import_path": import_path,
        "to_dir_path": dir_path,
    }


def _read_go_modules(repo_root: Path) -> tuple[GoModuleMetadata, ...]:
    repo = Repo(repo_root)
    go_mod_paths = sorted(
        entry.path
        for entry in list_head_tree_files(repo)
        if PurePosixPath(entry.path).name == "go.mod" and not _is_vendor_dir(_dir_path(entry.path))
    )

    return tuple(_read_go_module(repo_root, go_mod_path) for go_mod_path in go_mod_paths)


def _read_go_module(repo_root: Path, go_mod_path: str) -> GoModuleMetadata:
    go_mod = repo_root / go_mod_path
    root_dir = _dir_path(go_mod_path)

    module_path = None
    go_version = None
    toolchain = None
    for raw_line in go_mod.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.split("//", 1)[0].strip()
        if not line:
            continue

        parts = line.split()
        if len(parts) < 2:
            continue

        if parts[0] == "module" and module_path is None:
            module_path = _unquote_go_mod_value(parts[1])
        elif parts[0] == "go" and go_version is None:
            go_version = parts[1]
        elif parts[0] == "toolchain" and toolchain is None:
            toolchain = parts[1]

    return GoModuleMetadata(
        root_dir=root_dir,
        path=module_path,
        go_version=go_version,
        toolchain=toolchain,
        go_mod_path=go_mod_path,
    )


def _root_module_or_empty(modules: tuple[GoModuleMetadata, ...]) -> GoModuleMetadata:
    for module in modules:
        if module.root_dir == ".":
            return module

    return GoModuleMetadata(root_dir=".", path=None, go_version=None, toolchain=None, go_mod_path=None)


def _module_document(module: GoModuleMetadata) -> dict[str, Any]:
    return {
        "module_id": _module_id(module),
        "root_dir": module.root_dir,
        "path": module.path,
        "go_version": module.go_version,
        "toolchain": module.toolchain,
        "go_mod_path": module.go_mod_path,
    }


def _package_import_path(dir_path: str, module: GoModuleMetadata) -> str | None:
    if _is_vendor_dir(dir_path):
        return _vendor_import_path(dir_path)

    if module.path is None:
        return None

    relative_dir = _relative_to_module_root(module.root_dir, dir_path)
    if relative_dir is None:
        return None

    if relative_dir == ".":
        return module.path

    return f"{module.path}/{relative_dir}"


def _package_id(import_path: str | None, dir_path: str, package_name: str) -> str:
    return f"{import_path or dir_path}#{package_name}"


def _module_id(module: GoModuleMetadata) -> str:
    return module.path or module.root_dir


def _primary_package(packages: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(
        packages,
        key=lambda item: (
            item["is_vendor"],
            item["is_test_package"],
            item["name"].endswith("_test"),
            item["package_id"],
        ),
    )[0]


def _entrypoint_kind(
    dir_path: str,
    package_name: str,
    module: GoModuleMetadata,
) -> str | None:
    if package_name != "main":
        return None

    relative_dir = _relative_to_module_root(module.root_dir, dir_path) or dir_path
    if relative_dir == "cmd" or relative_dir.startswith("cmd/"):
        return "cmd"

    if relative_dir == ".":
        return "root"

    return "main"


def _module_for_dir(dir_path: str, modules: tuple[GoModuleMetadata, ...]) -> GoModuleMetadata:
    matches = [
        module
        for module in modules
        if _path_belongs_to_dir(dir_path, module.root_dir)
    ]
    if not matches:
        return GoModuleMetadata(root_dir=".", path=None, go_version=None, toolchain=None, go_mod_path=None)

    return sorted(
        matches,
        key=lambda module: (-len(PurePosixPath(module.root_dir).parts), module.root_dir),
    )[0]


def _module_for_import_path(
    import_path: str,
    modules: tuple[GoModuleMetadata, ...],
) -> GoModuleMetadata | None:
    matches = [
        module
        for module in modules
        if module.path is not None
        and (import_path == module.path or import_path.startswith(f"{module.path}/"))
    ]
    if not matches:
        return None

    return sorted(matches, key=lambda module: (-len(module.path or ""), module.root_dir))[0]


def _module_relative_dir(module: GoModuleMetadata, import_path: str) -> str:
    if import_path == module.path:
        return module.root_dir

    suffix = import_path.removeprefix(f"{module.path}/")
    if module.root_dir == ".":
        return suffix

    return f"{module.root_dir}/{suffix}"


def _relative_to_module_root(module_root: str, dir_path: str) -> str | None:
    if module_root == ".":
        return dir_path

    if dir_path == module_root:
        return "."

    if dir_path.startswith(f"{module_root}/"):
        return dir_path.removeprefix(f"{module_root}/")

    return None


def _resolve_relative_dir(from_dir_path: str, import_path: str) -> str | None:
    base = "" if from_dir_path == "." else from_dir_path
    normalized = posixpath.normpath(posixpath.join(base, import_path))
    if normalized == ".":
        return "."

    if normalized.startswith("../"):
        return None

    return normalized


def _looks_like_standard_library(import_path: str) -> bool:
    first_segment = import_path.split("/", 1)[0]
    return "." not in first_segment


def _path_belongs_to_dir(path: str, dir_path: str) -> bool:
    if dir_path == ".":
        return True

    return path == dir_path or path.startswith(f"{dir_path}/")


def _dir_path(path: str) -> str:
    parent = str(PurePosixPath(path).parent)
    return "." if parent == "." else parent


def _normalize_path(path: str) -> str:
    return str(PurePosixPath(path))


def _is_vendor_dir(dir_path: str) -> bool:
    return "vendor" in PurePosixPath(dir_path).parts


def _vendor_import_path(dir_path: str) -> str | None:
    parts = PurePosixPath(dir_path).parts
    if "vendor" not in parts:
        return None

    vendor_index = parts.index("vendor")
    rest = parts[vendor_index + 1 :]
    return "/".join(rest) if rest else None


def _unquote_go_mod_value(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "`"}:
        return value[1:-1]

    return value
