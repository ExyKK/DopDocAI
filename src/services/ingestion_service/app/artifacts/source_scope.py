from pathlib import PurePosixPath
from typing import Any

SOURCE_SCOPE_RUNTIME = "runtime"
SOURCE_SCOPE_TEST = "test"
SOURCE_SCOPE_GENERATED = "generated"
SOURCE_SCOPE_DOCS = "docs"
SOURCE_SCOPE_INFRA = "infra"
SOURCE_SCOPE_VENDOR = "vendor"

NON_RUNTIME_SOURCE_SCOPES = {
    SOURCE_SCOPE_TEST,
    SOURCE_SCOPE_GENERATED,
    SOURCE_SCOPE_DOCS,
    SOURCE_SCOPE_VENDOR,
}


def infer_source_scope(
    path: str,
    *,
    kind: str | None = None,
    is_generated: bool = False,
    is_generated_doc: bool = False,
    is_api_spec: bool = False,
    is_test: bool = False,
    is_vendor: bool = False,
) -> str:
    pure_path = PurePosixPath(path)

    if is_vendor or kind == "vendor" or _has_part(pure_path, "vendor"):
        return SOURCE_SCOPE_VENDOR
    if is_generated or is_generated_doc or is_api_spec or kind in {"generated", "api_spec"}:
        return SOURCE_SCOPE_GENERATED
    if is_test or kind == "test" or _is_test_path(pure_path):
        return SOURCE_SCOPE_TEST
    if _is_infra_path(pure_path):
        return SOURCE_SCOPE_INFRA
    if kind == "markdown" or _is_docs_path(pure_path):
        return SOURCE_SCOPE_DOCS

    return SOURCE_SCOPE_RUNTIME


def source_scope_from_record(record: dict[str, Any]) -> str:
    existing = record.get("source_scope")
    if isinstance(existing, str) and existing:
        return existing

    return infer_source_scope(
        str(record.get("path") or record.get("file_path") or ""),
        kind=record.get("kind"),
        is_generated=bool(record.get("is_generated")),
        is_generated_doc=bool(record.get("is_generated_doc")),
        is_api_spec=bool(record.get("is_api_spec")),
        is_test=bool(record.get("is_test")),
        is_vendor=bool(record.get("is_vendor")),
    )


def is_runtime_source_scope(source_scope: str | None) -> bool:
    return source_scope == SOURCE_SCOPE_RUNTIME


def runtime_scope_from_source_scope(source_scope: str | None) -> bool:
    return is_runtime_source_scope(source_scope)


def _is_test_path(path: PurePosixPath) -> bool:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    return (
        name.endswith("_test.go")
        or name.startswith("test_")
        or ".spec." in name
        or ".test." in name
        or "test" in parts
        or "tests" in parts
    )


def _is_docs_path(path: PurePosixPath) -> bool:
    parts = {part.lower() for part in path.parts}
    return bool(parts.intersection({"docs", "doc", "documentation", "site"}))


def _is_infra_path(path: PurePosixPath) -> bool:
    name = path.name.lower()
    parts = {part.lower() for part in path.parts}
    return (
        name == "dockerfile"
        or name.startswith("dockerfile.")
        or name.startswith("docker-compose")
        or name in {"compose.yaml", "compose.yml", "makefile", ".gitlab-ci.yml", ".gitlab-ci.yaml"}
        or bool(parts.intersection({".github", "deploy", "deployment", "k8s", "kubernetes", "terraform"}))
    )


def _has_part(path: PurePosixPath, part: str) -> bool:
    return part in {item.lower() for item in path.parts}
