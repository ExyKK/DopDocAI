import json
from dataclasses import dataclass
from typing import Any

from app.pipeline.evidence_pack import EvidencePack, EvidencePackSource, estimate_tokens

RENDERED_EVIDENCE_PACK_VERSION = 1
_MAX_TABLE_ROWS = 24
_MAX_LIST_ROWS = 40
_MAX_CELL_LENGTH = 140
_MAX_RETRIEVAL_CHARS = 6000


@dataclass(frozen=True)
class RenderedEvidenceSource:
    source_id: str
    source_kind: str
    title: str
    content_markdown: str
    estimated_tokens: int
    original_estimated_tokens: int
    file_path: str | None = None
    symbol_name: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    chunk_id: str | None = None
    score: float | None = None
    language: str | None = None
    source_scope: str | None = None
    warnings: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "title": self.title,
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_id": self.chunk_id,
            "score": self.score,
            "language": self.language,
            "source_scope": self.source_scope,
            "estimated_tokens": self.estimated_tokens,
            "original_estimated_tokens": self.original_estimated_tokens,
            "warnings": self.warnings or [],
            "content_markdown": self.content_markdown,
        }

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_kind": self.source_kind,
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "line_range": _line_range(self.start_line, self.end_line),
            "source_scope": self.source_scope,
            "content_markdown": self.content_markdown,
        }

    def to_source_index_item(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "title": self.title,
            "source_kind": self.source_kind,
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_id": self.chunk_id,
            "score": self.score,
            "language": self.language,
            "source_scope": self.source_scope,
        }


@dataclass(frozen=True)
class RenderedEvidencePack:
    schema_version: int
    section_key: str
    title: str
    ordinal: int
    estimated_tokens: int
    sources: list[RenderedEvidenceSource]
    warnings: list[str]
    raw_evidence_summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "section_key": self.section_key,
            "title": self.title,
            "ordinal": self.ordinal,
            "estimated_tokens": self.estimated_tokens,
            "warnings": self.warnings,
            "raw_evidence_summary": self.raw_evidence_summary,
            "sources": [source.to_dict() for source in self.sources],
            "source_index": [source.to_source_index_item() for source in self.sources],
        }

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "section_key": self.section_key,
            "title": self.title,
            "ordinal": self.ordinal,
            "sources": [source.to_prompt_dict() for source in self.sources],
            "source_index": [source.to_source_index_item() for source in self.sources],
            "warnings": self.warnings,
        }


def build_rendered_evidence_pack(pack: EvidencePack) -> RenderedEvidencePack:
    rendered_sources: list[RenderedEvidenceSource] = []
    warnings: list[str] = []
    for source in pack.sources:
        rendered = _render_source(source)
        rendered_sources.append(rendered)
        warnings.extend(f"{source.source_id}: {warning}" for warning in rendered.warnings or [])

    estimated_tokens = sum(source.estimated_tokens for source in rendered_sources)
    return RenderedEvidencePack(
        schema_version=RENDERED_EVIDENCE_PACK_VERSION,
        section_key=pack.section_key,
        title=pack.title,
        ordinal=pack.ordinal,
        estimated_tokens=estimated_tokens,
        sources=rendered_sources,
        warnings=warnings,
        raw_evidence_summary={
            "raw_sources_total": len(pack.sources),
            "raw_estimated_tokens": pack.estimated_tokens,
            "omitted_sources_total": len(pack.omitted_sources),
            "truncated_sources_total": len(pack.truncated_sources),
            "retrieval_query": pack.retrieval_query,
            "retrieval_error": pack.retrieval_error,
        },
    )


def build_rendered_evidence_pack_manifest(
    *,
    documentation_run_id: str,
    repository_id: str,
    snapshot_id: str,
    template_kind: str,
    packs: list[RenderedEvidencePack],
) -> dict[str, Any]:
    return {
        "schema_version": RENDERED_EVIDENCE_PACK_VERSION,
        "documentation_run_id": documentation_run_id,
        "repository_id": repository_id,
        "snapshot_id": snapshot_id,
        "template_kind": template_kind,
        "artifact_kind": "rendered_evidence_pack_manifest",
        "sections": [pack.to_dict() for pack in packs],
        "summary": {
            "sections_total": len(packs),
            "estimated_tokens_total": sum(pack.estimated_tokens for pack in packs),
            "sources_total": sum(len(pack.sources) for pack in packs),
            "warnings_total": sum(len(pack.warnings) for pack in packs),
        },
    }


def _render_source(source: EvidencePackSource) -> RenderedEvidenceSource:
    warnings: list[str] = []
    if source.source_kind == "structured_artifact":
        key, value = _parse_structured_content(source.content)
        artifact_kind = _artifact_kind_from_reason(source.selection_reason, key)
        title = f"{artifact_kind}.{key}"
        content = _render_structured_value(artifact_kind, key, value)
        if source.truncated:
            warnings.append("raw_source_truncated")
    else:
        title = _retrieval_title(source)
        content = _render_retrieval_source(source)
        if source.source_scope == "generated" or source.source_kind == "generated":
            warnings.append("generated_source")

    estimated = estimate_tokens(content)
    return RenderedEvidenceSource(
        source_id=source.source_id,
        source_kind=source.source_kind,
        title=title,
        file_path=source.file_path,
        symbol_name=source.symbol_name,
        start_line=source.start_line,
        end_line=source.end_line,
        chunk_id=source.chunk_id,
        score=source.score,
        language=source.language,
        source_scope=source.source_scope,
        estimated_tokens=estimated,
        original_estimated_tokens=source.estimated_tokens,
        warnings=warnings,
        content_markdown=content,
    )


def _parse_structured_content(content: str) -> tuple[str, Any]:
    key, separator, payload = content.partition(":\n")
    if not separator:
        return "content", content

    try:
        return key.strip(), json.loads(payload)
    except json.JSONDecodeError:
        return key.strip(), payload


def _artifact_kind_from_reason(reason: str, key: str) -> str:
    prefix = "structured "
    if reason.startswith(prefix):
        tail = reason[len(prefix) :]
        artifact, separator, _ = tail.partition(".")
        if separator and artifact:
            return artifact

    if key in {"modules", "packages", "edges", "entrypoint_packages"}:
        return "package_graph"
    if key in {"change_events", "commit_summary", "touched_file_summary", "touched_package_summary"}:
        return "commit_log"
    if key in {"env_vars", "flags", "config_files", "config_structs", "api_specs", "data_contracts"}:
        return "config_inventory"
    return "project_model"


def _render_structured_value(artifact_kind: str, key: str, value: Any) -> str:
    if artifact_kind == "commit_log":
        return _render_commit_value(key, value)
    if key == "workspace_units":
        return _render_workspace_units(value)
    if key in {"modules", "packages", "entrypoint_packages"}:
        return _render_package_rows(key, value)
    if key == "edges":
        return _render_edges(value)
    if key == "http_surface":
        return _render_http_surface(value)
    if key == "api_specs":
        return _render_api_specs(value)
    if key in {"env_vars", "flags", "config_files", "config_structs", "data_contracts", "dependency_locks"}:
        return _render_config_rows(key, value)
    if key in {"integrations", "external_integrations"}:
        return _render_generic_rows("Integrations", value)
    if key in {"diagnostics", "unsupported_patterns", "truncated"}:
        return _render_generic_rows(key.replace("_", " ").title(), value)
    return _render_generic_value(key.replace("_", " ").title(), value)


def _render_workspace_units(value: Any) -> str:
    rows = _as_dicts(value)
    headers = ["unit", "kind", "root", "roles", "frameworks", "files", "key files"]
    table = [
        [
            _pick(row, "name", "workspace_unit_id"),
            _cell(row.get("unit_kind")),
            _cell(row.get("root_path")),
            _join(row.get("roles")),
            _join(row.get("frameworks")),
            _nested(row, "file_counts.files_total"),
            _paths(row.get("key_files"), limit=4),
        ]
        for row in rows[:_MAX_TABLE_ROWS]
    ]
    return _section_with_table("Workspace units", headers, table, rows)


def _render_package_rows(key: str, value: Any) -> str:
    rows = _as_dicts(value)
    headers = ["package", "dir", "module", "runtime", "files"]
    table = [
        [
            _pick(row, "name", "package_id"),
            _cell(row.get("dir_path")),
            _cell(row.get("module_path") or row.get("import_path")),
            _cell(row.get("runtime_scope") or row.get("source_scope")),
            _cell(row.get("files_total") or len(row.get("files", []) or [])),
        ]
        for row in rows[:_MAX_TABLE_ROWS]
    ]
    return _section_with_table(key.replace("_", " ").title(), headers, table, rows)


def _render_edges(value: Any) -> str:
    rows = _as_dicts(value)
    headers = ["from", "to", "kind"]
    table = [
        [
            _pick(row, "from_package_id", "from", "source"),
            _pick(row, "to_package_id", "to", "target"),
            _pick(row, "edge_kind", "kind", "relationship"),
        ]
        for row in rows[:_MAX_TABLE_ROWS]
    ]
    return _section_with_table("Package graph edges", headers, table, rows)


def _render_http_surface(value: Any) -> str:
    if not isinstance(value, dict):
        return _render_generic_value("HTTP surface", value)

    lines = ["HTTP surface:"]
    lines.extend(_bullet("detected", value.get("detected")))
    lines.extend(_bullet("frameworks", _join(value.get("frameworks"))))
    lines.extend(_bullet("routes_total", value.get("routes_total") or len(value.get("routes", []) or [])))
    routes = _as_dicts(value.get("routes"))
    if routes:
        rows = [
            [
                _pick(route, "method", "http_method"),
                _pick(route, "path", "route_path", "pattern"),
                _pick(route, "handler", "handler_name", "symbol_name"),
                _pick(route, "file_path", "source_file"),
            ]
            for route in routes[:_MAX_TABLE_ROWS]
        ]
        lines.extend(["", *_table(["method", "path", "handler", "file"], rows)])
        lines.extend(_omitted_note(routes))
    return "\n".join(lines)


def _render_api_specs(value: Any) -> str:
    rows = _as_dicts(value)
    headers = ["path", "kind", "scope", "routes", "definitions"]
    table = [
        [
            _pick(row, "path", "file_path"),
            _pick(row, "spec_kind", "format", "kind"),
            _cell(row.get("source_scope")),
            _cell(_nested(row, "summary.routes_total") or row.get("routes_total")),
            _cell(_nested(row, "summary.definitions_total") or row.get("definitions_total")),
        ]
        for row in rows[:_MAX_TABLE_ROWS]
    ]
    return _section_with_table("API specs", headers, table, rows)


def _render_config_rows(key: str, value: Any) -> str:
    rows = _as_dicts(value)
    if key == "env_vars":
        headers = ["key", "required", "default", "source"]
        table = [
            [
                _pick(row, "key", "name"),
                _cell(row.get("required")),
                _cell(row.get("default_value") or row.get("default")),
                _source_path(row),
            ]
            for row in rows[:_MAX_TABLE_ROWS]
        ]
    elif key == "flags":
        headers = ["flag", "required", "default", "source"]
        table = [
            [
                _pick(row, "name", "key"),
                _cell(row.get("required")),
                _cell(row.get("default_value") or row.get("default")),
                _source_path(row),
            ]
            for row in rows[:_MAX_TABLE_ROWS]
        ]
    elif key == "config_files":
        headers = ["path", "format", "scope", "keys"]
        table = [
            [
                _pick(row, "path", "file_path"),
                _cell(row.get("format")),
                _cell(row.get("source_scope")),
                _join(row.get("keys"), limit=8),
            ]
            for row in rows[:_MAX_TABLE_ROWS]
        ]
    elif key in {"config_structs", "data_contracts"}:
        headers = ["name", "kind", "fields", "source"]
        table = [
            [
                _pick(row, "name", "model_name"),
                _pick(row, "model_kind", "kind"),
                _field_names(row.get("fields")),
                _source_path(row),
            ]
            for row in rows[:_MAX_TABLE_ROWS]
        ]
    else:
        headers = ["path", "kind", "scope", "items"]
        table = [
            [
                _pick(row, "path", "file_path"),
                _pick(row, "lockfile_kind", "kind", "format"),
                _cell(row.get("source_scope")),
                _cell(row.get("dependencies_total") or row.get("packages_total")),
            ]
            for row in rows[:_MAX_TABLE_ROWS]
        ]
    return _section_with_table(key.replace("_", " ").title(), headers, table, rows)


def _render_commit_value(key: str, value: Any) -> str:
    if key == "commit_summary":
        return _render_generic_value("Commit log summary", value)
    if key == "change_events":
        return _render_change_events(value)
    if key == "touched_file_summary":
        return _render_touched_files(value)
    if key == "touched_package_summary":
        return _render_touched_packages(value)
    if key == "merge_commit_summary":
        return _render_merge_commits(value)
    return _render_generic_value(key.replace("_", " ").title(), value)


def _render_change_events(value: Any) -> str:
    rows = _as_dicts(value)
    headers = ["sha", "type", "path", "current", "subject"]
    table = [
        [
            _pick(row, "short_sha", "sha"),
            _pick(row, "change_type", "status"),
            _cell(row.get("path")),
            _cell(row.get("current_file_state")),
            _cell(row.get("subject")),
        ]
        for row in rows[:_MAX_LIST_ROWS]
    ]
    lines = [
        "Recent change events. Each row is one file-level history fact.",
        "Do not infer current file absence from a historical deletion unless current=absent.",
        "",
        *_table(headers, table),
    ]
    lines.extend(_omitted_note(rows, limit=_MAX_LIST_ROWS))
    return "\n".join(lines)


def _render_touched_files(value: Any) -> str:
    rows = _as_dicts(value)
    headers = ["path", "current", "changes", "latest"]
    table = [
        [
            _cell(row.get("path")),
            _cell(row.get("current_file_state")),
            _render_counts(row.get("change_type_counts")),
            _short_sha(row.get("latest_commit_sha")),
        ]
        for row in rows[:_MAX_TABLE_ROWS]
    ]
    return _section_with_table("Touched files", headers, table, rows)


def _render_touched_packages(value: Any) -> str:
    rows = _as_dicts(value)
    headers = ["package", "dir", "files", "changes"]
    table = [
        [
            _pick(row, "name", "package_id"),
            _cell(row.get("dir_path")),
            _cell(row.get("files_total")),
            _render_counts(row.get("change_type_counts")),
        ]
        for row in rows[:_MAX_TABLE_ROWS]
    ]
    return _section_with_table("Touched packages", headers, table, rows)


def _render_merge_commits(value: Any) -> str:
    rows = _as_dicts(value)
    headers = ["sha", "parents", "subject"]
    table = [
        [
            _pick(row, "short_sha", "sha"),
            _cell(row.get("parents_total")),
            _cell(row.get("subject")),
        ]
        for row in rows[:_MAX_TABLE_ROWS]
    ]
    return _section_with_table("Merge commits", headers, table, rows)


def _render_retrieval_source(source: EvidencePackSource) -> str:
    lines = [
        f"Retrieved source {source.source_id}:",
        *_bullet("file", source.file_path),
        *_bullet("symbol", source.symbol_name),
        *_bullet("lines", _line_range(source.start_line, source.end_line)),
        *_bullet("kind", source.source_kind),
        *_bullet("scope", source.source_scope),
        *_bullet("score", source.score),
        "",
        "Excerpt:",
        "```text",
        _truncate(source.content, _MAX_RETRIEVAL_CHARS),
        "```",
    ]
    return "\n".join(lines)


def _render_generic_rows(title: str, value: Any) -> str:
    rows = _as_dicts(value)
    if rows:
        keys = _stable_keys(rows)
        table = [[_cell(row.get(key)) for key in keys] for row in rows[:_MAX_TABLE_ROWS]]
        return _section_with_table(title, keys, table, rows)
    return _render_generic_value(title, value)


def _render_generic_value(title: str, value: Any) -> str:
    if isinstance(value, dict):
        lines = [f"{title}:"]
        for key, item in list(value.items())[:_MAX_TABLE_ROWS]:
            lines.append(f"- {key}: {_cell(item)}")
        if len(value) > _MAX_TABLE_ROWS:
            lines.append(f"- ... {len(value) - _MAX_TABLE_ROWS} more keys omitted")
        return "\n".join(lines)
    if isinstance(value, list):
        rows = _as_dicts(value)
        if rows:
            return _render_generic_rows(title, value)
        lines = [f"{title}:"]
        for item in value[:_MAX_LIST_ROWS]:
            lines.append(f"- {_cell(item)}")
        if len(value) > _MAX_LIST_ROWS:
            lines.append(f"- ... {len(value) - _MAX_LIST_ROWS} more items omitted")
        return "\n".join(lines)
    return f"{title}: {_cell(value)}"


def _section_with_table(title: str, headers: list[str], rows: list[list[Any]], original_rows: list[Any]) -> str:
    lines = [f"{title}:"]
    if rows:
        lines.extend(["", *_table(headers, rows)])
        lines.extend(_omitted_note(original_rows))
    else:
        lines.append("- no rows")
    return "\n".join(lines)


def _table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    return [
        "| " + " | ".join(_escape_cell(header) for header in headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(_escape_cell(cell) for cell in row) + " |" for row in rows),
    ]


def _as_dicts(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _stable_keys(rows: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for row in rows[:_MAX_TABLE_ROWS]:
        for key in row:
            if key not in seen and len(seen) < 5:
                seen.append(key)
    return seen or ["value"]


def _omitted_note(rows: list[Any], *, limit: int = _MAX_TABLE_ROWS) -> list[str]:
    if len(rows) <= limit:
        return []
    return ["", f"_Omitted {len(rows) - limit} additional rows from rendered evidence._"]


def _retrieval_title(source: EvidencePackSource) -> str:
    if source.file_path:
        line_range = _line_range(source.start_line, source.end_line)
        return f"{source.file_path}{':' + line_range if line_range else ''}"
    if source.symbol_name:
        return source.symbol_name
    return source.selection_reason


def _pick(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return _cell(value)
    return ""


def _nested(row: dict[str, Any], path: str) -> Any:
    value: Any = row
    for part in path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _source_path(row: dict[str, Any]) -> str:
    source = row.get("source")
    if isinstance(source, dict):
        return _cell(source.get("file_path"))
    return _pick(row, "file_path", "path")


def _paths(value: Any, *, limit: int) -> str:
    rows = _as_dicts(value)
    if rows:
        return _join([_pick(row, "path", "file_path") for row in rows], limit=limit)
    return _join(value, limit=limit)


def _field_names(value: Any) -> str:
    rows = _as_dicts(value)
    return _join([_pick(row, "name", "json_name", "field_name") for row in rows], limit=10)


def _render_counts(value: Any) -> str:
    if not isinstance(value, dict):
        return _cell(value)
    return ", ".join(f"{key}={item}" for key, item in sorted(value.items()))


def _short_sha(value: Any) -> str:
    text = _cell(value)
    return text[:12] if len(text) > 12 else text


def _join(value: Any, *, limit: int = 6) -> str:
    if value is None:
        return ""
    if isinstance(value, list | tuple | set):
        items = [_cell(item) for item in list(value)[:limit] if _cell(item)]
        suffix = f", +{len(value) - limit}" if len(value) > limit else ""
        return ", ".join(items) + suffix
    return _cell(value)


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list | tuple | set):
        return _join(value)
    if isinstance(value, dict):
        compact = ", ".join(f"{key}={_cell(item)}" for key, item in list(value.items())[:4])
        if len(value) > 4:
            compact += ", ..."
        return _truncate(compact, _MAX_CELL_LENGTH)
    return _truncate(str(value).replace("\n", " "), _MAX_CELL_LENGTH)


def _escape_cell(value: Any) -> str:
    return _cell(value).replace("|", "\\|")


def _bullet(label: str, value: Any) -> list[str]:
    text = _cell(value)
    return [f"- {label}: {text}"] if text else []


def _line_range(start_line: int | None, end_line: int | None) -> str | None:
    if start_line is None and end_line is None:
        return None
    if start_line is None:
        return str(end_line)
    if end_line is None or end_line == start_line:
        return str(start_line)
    return f"{start_line}-{end_line}"


def _truncate(value: str, max_length: int) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 14].rstrip() + "\n[truncated]"
