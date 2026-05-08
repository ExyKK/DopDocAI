import hashlib
import json
import uuid
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from app.artifacts.models import BuiltAnalysisArtifact

MAX_SYMBOL_CHUNK_LINES = 120
SYMBOL_CHUNK_OVERLAP_LINES = 10
MAX_TEXT_CHUNK_LINES = 120
TEXT_CHUNK_OVERLAP_LINES = 20
MAX_TEXT_FILE_BYTES = 512 * 1024
MAX_TEXT_FILE_CHUNKS = 24

_CHUNK_NAMESPACE = uuid.UUID("f7e5f4a2-f31f-44ec-a5d0-54d9de02e4ad")
_SKIPPED_FILE_KINDS = {"binary", "vendor", "dependency_lock"}


@dataclass(frozen=True)
class CodeChunk:
    chunk_id: str
    text: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class CodeChunkBuildResult:
    chunks: tuple[CodeChunk, ...]
    stats: dict[str, Any]
    symbol_chunk_map: dict[str, tuple[str, ...]]


def build_code_chunks(
    repo_path: str | Path,
    *,
    repository_id: str,
    snapshot_id: str,
    snapshot_metadata: dict[str, Any],
    artifacts: tuple[BuiltAnalysisArtifact, ...],
) -> CodeChunkBuildResult:
    repo_root = Path(repo_path)
    documents = _load_artifact_documents(artifacts)
    file_inventory = documents.get("file_inventory", {})
    go_symbols = documents.get("go_symbols", {})
    package_graph = documents.get("package_graph", {})
    project_model = documents.get("project_model", {})

    file_records = {
        _normalize_path(file_record["path"]): file_record
        for file_record in file_inventory.get("files", [])
        if file_record.get("path")
    }
    package_by_file = _build_package_lookup(package_graph)
    workspace_units = project_model.get("workspace_units", [])
    commit_sha = str(snapshot_metadata["commit_sha"])

    chunks: list[CodeChunk] = []
    symbol_chunk_map: dict[str, list[str]] = defaultdict(list)
    go_files_with_symbol_chunks: set[str] = set()
    skipped_files = Counter()

    for symbol in sorted(
        go_symbols.get("symbols", []),
        key=lambda item: (
            item.get("file_path", ""),
            item.get("start_line", 0),
            item.get("end_line", 0),
            item.get("kind", ""),
            item.get("qualified_name", ""),
        ),
    ):
        file_path = _normalize_path(symbol.get("file_path", ""))
        if not file_path:
            continue

        file_record = file_records.get(file_path, {})
        package_ref = package_by_file.get(file_path)
        workspace_unit_id = _workspace_unit_for_path(file_path, workspace_units)
        source_scope = str(symbol.get("source_scope") or file_record.get("source_scope") or "runtime")
        is_test = bool(symbol.get("is_test") or file_record.get("is_test") or source_scope == "test")
        symbol_signature = _symbol_signature(symbol)
        symbol_id = str(symbol.get("symbol_id") or _stable_hash(file_path, symbol_signature))
        source_lines = _read_lines(repo_root / file_path)
        start_line = _positive_int(symbol.get("start_line"), 1)
        end_line = _positive_int(symbol.get("end_line"), start_line)
        excerpt_lines = source_lines[start_line - 1 : end_line] if source_lines else []
        line_windows = _line_windows(
            excerpt_lines,
            first_line=start_line,
            max_lines=MAX_SYMBOL_CHUNK_LINES,
            overlap_lines=SYMBOL_CHUNK_OVERLAP_LINES,
            max_chunks=MAX_TEXT_FILE_CHUNKS,
        )
        if not line_windows:
            line_windows = ((start_line, end_line, ""),)

        go_files_with_symbol_chunks.add(file_path)
        for chunk_index, (chunk_start, chunk_end, source_text) in enumerate(line_windows):
            chunk_text = _go_symbol_chunk_text(
                symbol=symbol,
                file_path=file_path,
                package_ref=package_ref,
                chunk_index=chunk_index,
                start_line=chunk_start,
                end_line=chunk_end,
                source_text=source_text,
            )
            chunk_id = deterministic_chunk_id(
                snapshot_id=snapshot_id,
                file_path=file_path,
                symbol_signature=symbol_signature,
                chunk_index=chunk_index,
            )
            payload = _payload(
                chunk_id=chunk_id,
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                commit_sha=commit_sha,
                file_path=file_path,
                language="go",
                workspace_unit_id=workspace_unit_id,
                package_ref=package_ref,
                kind=str(symbol.get("kind") or "symbol"),
                name=str(symbol.get("qualified_name") or symbol.get("name") or ""),
                start_line=chunk_start,
                end_line=chunk_end,
                chunk_kind="go_symbol",
                is_test=is_test,
                source_scope=source_scope,
                text=chunk_text,
                symbol_id=symbol_id,
                symbol_signature=symbol_signature,
            )
            chunks.append(CodeChunk(chunk_id=chunk_id, text=chunk_text, payload=payload))
            symbol_chunk_map[symbol_id].append(chunk_id)

    for file_path in sorted(file_records):
        file_record = file_records[file_path]
        skip_reason = _skip_text_file_reason(file_record, file_path, go_files_with_symbol_chunks)
        if skip_reason is not None:
            skipped_files[skip_reason] += 1
            continue

        read_result = _read_text_prefix(repo_root / file_path)
        if read_result is None:
            skipped_files["missing_or_unreadable"] += 1
            continue

        text, truncated = read_result
        if not text.strip():
            skipped_files["empty_text"] += 1
            continue

        package_ref = package_by_file.get(file_path)
        workspace_unit_id = _workspace_unit_for_path(file_path, workspace_units)
        source_scope = str(file_record.get("source_scope") or "runtime")
        is_test = bool(file_record.get("is_test") or source_scope == "test")
        file_kind = str(file_record.get("kind") or "other")
        language = _language_for_file(file_path, file_kind)
        line_windows = _line_windows(
            text.splitlines(),
            first_line=1,
            max_lines=MAX_TEXT_CHUNK_LINES,
            overlap_lines=TEXT_CHUNK_OVERLAP_LINES,
            max_chunks=MAX_TEXT_FILE_CHUNKS,
        )

        for chunk_index, (start_line, end_line, source_text) in enumerate(line_windows):
            chunk_text = _file_slice_chunk_text(
                file_path=file_path,
                file_kind=file_kind,
                source_scope=source_scope,
                chunk_index=chunk_index,
                start_line=start_line,
                end_line=end_line,
                truncated=truncated,
                source_text=source_text,
            )
            chunk_id = deterministic_chunk_id(
                snapshot_id=snapshot_id,
                file_path=file_path,
                symbol_signature=f"file:{file_path}",
                chunk_index=chunk_index,
            )
            payload = _payload(
                chunk_id=chunk_id,
                repository_id=repository_id,
                snapshot_id=snapshot_id,
                commit_sha=commit_sha,
                file_path=file_path,
                language=language,
                workspace_unit_id=workspace_unit_id,
                package_ref=package_ref,
                kind=file_kind,
                name=PurePosixPath(file_path).name,
                start_line=start_line,
                end_line=end_line,
                chunk_kind="file_slice",
                is_test=is_test,
                source_scope=source_scope,
                text=chunk_text,
                symbol_id=None,
                symbol_signature=None,
            )
            chunks.append(CodeChunk(chunk_id=chunk_id, text=chunk_text, payload=payload))

    chunks.sort(key=lambda item: (item.payload["file_path"], item.payload.get("start_line", 0), item.chunk_id))
    stats = _build_stats(chunks, skipped_files, symbol_chunk_map)
    return CodeChunkBuildResult(
        chunks=tuple(chunks),
        stats=stats,
        symbol_chunk_map={key: tuple(value) for key, value in sorted(symbol_chunk_map.items())},
    )


def deterministic_chunk_id(
    *,
    snapshot_id: str,
    file_path: str,
    symbol_signature: str,
    chunk_index: int,
) -> str:
    key = json.dumps(
        {
            "snapshot_id": snapshot_id,
            "file_path": _normalize_path(file_path),
            "symbol_signature": symbol_signature,
            "chunk_index": chunk_index,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return str(uuid.uuid5(_CHUNK_NAMESPACE, key))


def _load_artifact_documents(artifacts: tuple[BuiltAnalysisArtifact, ...]) -> dict[str, dict[str, Any]]:
    documents: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        try:
            documents[artifact.artifact_kind] = json.loads(artifact.payload.decode("utf-8"))
        except json.JSONDecodeError:
            documents[artifact.artifact_kind] = {}
    return documents


def _build_package_lookup(package_graph: dict[str, Any]) -> dict[str, dict[str, Any]]:
    package_by_file: dict[str, dict[str, Any]] = {}
    for package in package_graph.get("packages", []):
        package_ref = _compact_package_ref(package)
        for file_path in package.get("files", []):
            package_by_file[_normalize_path(file_path)] = package_ref
    return package_by_file


def _compact_package_ref(package: dict[str, Any]) -> dict[str, Any]:
    return _drop_none(
        {
            "package_id": package.get("package_id"),
            "name": package.get("name"),
            "import_path": package.get("import_path"),
            "dir_path": package.get("dir_path"),
            "module_path": package.get("module_path"),
        }
    )


def _workspace_unit_for_path(file_path: str, workspace_units: list[dict[str, Any]]) -> str | None:
    candidates = [
        unit
        for unit in workspace_units
        if unit.get("workspace_unit_id") and _path_under_root(file_path, str(unit.get("root_path") or "."))
    ]
    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (len(str(item.get("root_path") or ".")), str(item["workspace_unit_id"])),
        reverse=True,
    )
    return str(candidates[0]["workspace_unit_id"])


def _path_under_root(file_path: str, root_path: str) -> bool:
    normalized_file = _normalize_path(file_path)
    normalized_root = _normalize_path(root_path or ".")
    if normalized_root == ".":
        return True
    return normalized_file == normalized_root or normalized_file.startswith(f"{normalized_root}/")


def _symbol_signature(symbol: dict[str, Any]) -> str:
    return str(
        symbol.get("signature")
        or symbol.get("qualified_name")
        or symbol.get("name")
        or symbol.get("symbol_id")
        or "symbol"
    )


def _go_symbol_chunk_text(
    *,
    symbol: dict[str, Any],
    file_path: str,
    package_ref: dict[str, Any] | None,
    chunk_index: int,
    start_line: int,
    end_line: int,
    source_text: str,
) -> str:
    header = [
        f"Go {symbol.get('kind') or 'symbol'}: {symbol.get('qualified_name') or symbol.get('name')}",
        f"File: {file_path}:{start_line}-{end_line}",
        f"Chunk: {chunk_index}",
    ]
    if package_ref:
        header.append(f"Package: {package_ref.get('package_id') or package_ref.get('name')}")
    if symbol.get("signature"):
        header.append(f"Signature: {symbol['signature']}")
    if symbol.get("doc_comment"):
        header.append(f"Doc: {symbol['doc_comment']}")

    if source_text.strip():
        return "\n".join([*header, "Source:", source_text]).strip()
    return "\n".join(header).strip()


def _file_slice_chunk_text(
    *,
    file_path: str,
    file_kind: str,
    source_scope: str,
    chunk_index: int,
    start_line: int,
    end_line: int,
    truncated: bool,
    source_text: str,
) -> str:
    header = [
        f"File: {file_path}:{start_line}-{end_line}",
        f"Kind: {file_kind}",
        f"Source scope: {source_scope}",
        f"Chunk: {chunk_index}",
    ]
    if truncated:
        header.append("Truncated: true")
    return "\n".join([*header, "Source:", source_text]).strip()


def _payload(
    *,
    chunk_id: str,
    repository_id: str,
    snapshot_id: str,
    commit_sha: str,
    file_path: str,
    language: str,
    workspace_unit_id: str | None,
    package_ref: dict[str, Any] | None,
    kind: str,
    name: str | None,
    start_line: int | None,
    end_line: int | None,
    chunk_kind: str,
    is_test: bool,
    source_scope: str,
    text: str,
    symbol_id: str | None,
    symbol_signature: str | None,
) -> dict[str, Any]:
    payload = {
        "chunk_id": chunk_id,
        "snapshot_id": snapshot_id,
        "repository_id": repository_id,
        "commit_sha": commit_sha,
        "file_path": file_path,
        "language": language,
        "kind": kind,
        "chunk_kind": chunk_kind,
        "is_test": is_test,
        "source_scope": source_scope,
        "text": text,
    }
    if workspace_unit_id:
        payload["workspace_unit_id"] = workspace_unit_id
    if package_ref:
        payload["package"] = package_ref
        if package_ref.get("package_id"):
            payload["package_id"] = package_ref["package_id"]
    if name:
        payload["name"] = name
    if start_line is not None:
        payload["start_line"] = start_line
    if end_line is not None:
        payload["end_line"] = end_line
    if symbol_id:
        payload["symbol_id"] = symbol_id
    if symbol_signature:
        payload["symbol_signature"] = symbol_signature
    return payload


def _line_windows(
    lines: list[str],
    *,
    first_line: int,
    max_lines: int,
    overlap_lines: int,
    max_chunks: int,
) -> tuple[tuple[int, int, str], ...]:
    if not lines:
        return ()

    windows: list[tuple[int, int, str]] = []
    step = max(1, max_lines - overlap_lines)
    start = 0
    while start < len(lines) and len(windows) < max_chunks:
        end = min(len(lines), start + max_lines)
        start_line = first_line + start
        end_line = first_line + end - 1
        windows.append((start_line, end_line, "\n".join(lines[start:end]).strip()))
        if end >= len(lines):
            break
        start += step
    return tuple(windows)


def _skip_text_file_reason(
    file_record: dict[str, Any],
    file_path: str,
    go_files_with_symbol_chunks: set[str],
) -> str | None:
    if bool(file_record.get("is_binary")):
        return "binary"
    if bool(file_record.get("is_vendor")):
        return "vendor"
    kind = str(file_record.get("kind") or "other")
    if kind in _SKIPPED_FILE_KINDS:
        return kind
    if kind == "go" and file_path in go_files_with_symbol_chunks:
        return "represented_by_go_symbols"
    return None


def _read_lines(path: Path) -> list[str]:
    read_result = _read_text_prefix(path, max_bytes=1024 * 1024)
    if read_result is None:
        return []
    return read_result[0].splitlines()


def _read_text_prefix(path: Path, max_bytes: int = MAX_TEXT_FILE_BYTES) -> tuple[str, bool] | None:
    try:
        with path.open("rb") as file:
            raw = file.read(max_bytes + 1)
    except OSError:
        return None

    truncated = len(raw) > max_bytes
    if truncated:
        raw = raw[:max_bytes]
    return raw.decode("utf-8", errors="replace"), truncated


def _language_for_file(file_path: str, file_kind: str) -> str:
    suffix = PurePosixPath(file_path).suffix.lower()
    if suffix == ".go":
        return "go"
    if suffix in {".md", ".markdown", ".mdx"}:
        return "markdown"
    if suffix in {".yaml", ".yml"}:
        return "yaml"
    if suffix == ".json":
        return "json"
    if suffix == ".toml":
        return "toml"
    if suffix in {".js", ".jsx", ".mjs", ".cjs"}:
        return "javascript"
    if suffix in {".ts", ".tsx", ".mts", ".cts"}:
        return "typescript"
    if suffix == ".css":
        return "css"
    if suffix in {".html", ".htm"}:
        return "html"
    if suffix == ".sql":
        return "sql"
    return file_kind


def _build_stats(
    chunks: list[CodeChunk],
    skipped_files: Counter[str],
    symbol_chunk_map: dict[str, list[str]],
) -> dict[str, Any]:
    by_chunk_kind = Counter(str(chunk.payload.get("chunk_kind")) for chunk in chunks)
    by_language = Counter(str(chunk.payload.get("language")) for chunk in chunks)
    by_source_scope = Counter(str(chunk.payload.get("source_scope")) for chunk in chunks)
    by_workspace_unit = Counter(
        str(chunk.payload["workspace_unit_id"]) for chunk in chunks if chunk.payload.get("workspace_unit_id")
    )

    return {
        "chunks_total": len(chunks),
        "symbol_chunks_total": by_chunk_kind.get("go_symbol", 0),
        "file_slice_chunks_total": by_chunk_kind.get("file_slice", 0),
        "symbols_linked_total": len(symbol_chunk_map),
        "by_chunk_kind": dict(sorted(by_chunk_kind.items())),
        "by_language": dict(sorted(by_language.items())),
        "by_source_scope": dict(sorted(by_source_scope.items())),
        "by_workspace_unit": dict(sorted(by_workspace_unit.items())),
        "skipped_files": dict(sorted(skipped_files.items())),
    }


def _normalize_path(path: str) -> str:
    normalized = PurePosixPath(str(path).replace("\\", "/")).as_posix()
    if normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized or "."


def _positive_int(value: Any, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed > 0 else fallback


def _drop_none(value: dict[str, Any]) -> dict[str, Any]:
    return {key: item for key, item in value.items() if item is not None}


def _stable_hash(*parts: str) -> str:
    payload = "\0".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
