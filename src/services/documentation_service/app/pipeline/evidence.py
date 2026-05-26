from dataclasses import dataclass, field
from typing import Any

from app.infra.retrieval_client import RetrievalClient, RetrievalClientError, RetrievedSource
from app.pipeline.evidence_pack import EvidencePack, EvidencePackBudget, build_evidence_pack
from app.pipeline.rendered_evidence import RenderedEvidencePack, build_rendered_evidence_pack
from app.pipeline.templates import SectionTemplate


@dataclass
class SectionEvidence:
    section_key: str
    title: str
    ordinal: int
    status: str
    sources: list[dict[str, Any]]
    evidence: dict[str, Any] = field(default_factory=dict)
    evidence_pack: EvidencePack | None = None
    rendered_evidence_pack: RenderedEvidencePack | None = None
    prompt_contract: dict[str, Any] | None = None
    section_spec: dict[str, Any] = field(default_factory=dict)

    def to_request(self) -> dict[str, Any]:
        return {
            "section_key": self.section_key,
            "title": self.title,
            "ordinal": self.ordinal,
            "status": self.status,
            "sources": self.sources,
        }


class EvidencePlanner:
    def __init__(self, retrieval: RetrievalClient | None, *, budget: EvidencePackBudget | None = None):
        self._retrieval = retrieval
        self._budget = budget or EvidencePackBudget()

    def plan(
        self,
        *,
        snapshot_id: str,
        templates: tuple[SectionTemplate, ...],
        artifacts: dict[str, Any],
    ) -> list[SectionEvidence]:
        sections: list[SectionEvidence] = []
        for ordinal, template in enumerate(templates, start=1):
            builder = _SectionBuilder(snapshot_id=snapshot_id, template=template, ordinal=ordinal)
            _add_structured_evidence(builder, artifacts)
            if self._retrieval is not None and _should_use_retrieval(template.key, builder.sources):
                _add_retrieval_evidence(builder, self._retrieval)
            section = builder.build()
            section.evidence_pack = build_evidence_pack(
                section_key=section.section_key,
                title=section.title,
                ordinal=section.ordinal,
                evidence=section.evidence,
                sources=section.sources,
                budget=self._budget,
            )
            section.rendered_evidence_pack = build_rendered_evidence_pack(section.evidence_pack)
            sections.append(section)

        return sections


class _SectionBuilder:
    def __init__(self, *, snapshot_id: str, template: SectionTemplate, ordinal: int):
        self.snapshot_id = snapshot_id
        self.template = template
        self.ordinal = ordinal
        self.sources: list[dict[str, Any]] = []
        self.evidence: dict[str, Any] = {}
        self._seen_sources: set[tuple[Any, ...]] = set()

    def add_artifact_source(self, artifact_kind: str, note: str) -> None:
        self._add_source(
            {
                "snapshot_id": self.snapshot_id,
                "source_kind": "analysis_artifact",
                "file_path": None,
                "symbol_name": None,
                "start_line": None,
                "end_line": None,
                "chunk_id": None,
                "score": None,
                "note": f"{artifact_kind}: {note}",
            }
        )

    def add_file_source(self, file_path: str | None, note: str) -> None:
        if not file_path:
            return

        self._add_source(
            {
                "snapshot_id": self.snapshot_id,
                "source_kind": "file",
                "file_path": file_path,
                "symbol_name": None,
                "start_line": None,
                "end_line": None,
                "chunk_id": None,
                "score": None,
                "note": note,
            }
        )

    def add_retrieved_source(self, source: RetrievedSource, query: str) -> None:
        self._add_source(
            {
                "snapshot_id": self.snapshot_id,
                "source_kind": _source_kind(source.source_kind),
                "file_path": source.file_path,
                "symbol_name": source.symbol_name,
                "start_line": source.start_line,
                "end_line": source.end_line,
                "chunk_id": source.chunk_id,
                "score": source.score,
                "language": source.language,
                "source_scope": source.source_scope,
                "workspace_unit_id": source.workspace_unit_id,
                "package_id": source.package_id,
                "note": f"retrieval: {query}",
            }
        )

    def build(self) -> SectionEvidence:
        return SectionEvidence(
            section_key=self.template.key,
            title=self.template.title,
            ordinal=self.ordinal,
            section_spec=self.template.to_prompt_dict(),
            status="evidence_ready",
            sources=self.sources,
            evidence=self.evidence,
        )

    def _add_source(self, source: dict[str, Any]) -> None:
        if len(self.sources) >= 40:
            return

        key = (
            source.get("source_kind"),
            source.get("file_path"),
            source.get("symbol_name"),
            source.get("chunk_id"),
            source.get("note"),
        )
        if key in self._seen_sources:
            return

        self._seen_sources.add(key)
        source["ordinal"] = len(self.sources) + 1
        self.sources.append(source)


def _add_structured_evidence(builder: _SectionBuilder, artifacts: dict[str, Any]) -> None:
    project_model = artifacts.get("project_model") or {}
    package_graph = artifacts.get("package_graph") or {}
    config_inventory = artifacts.get("config_inventory") or {}
    commit_log = artifacts.get("commit_log") or {}
    current_file_index = _current_file_index(project_model)

    key = builder.template.key
    if key == "overview":
        _from_project_model(
            builder,
            project_model,
            [
                "summary",
                "repository_layout",
                "workspace_units",
                "go",
                "code_outline",
                "configuration",
                "external_integrations",
                "http_surface",
                "important_packages",
                "integrations",
            ],
        )
        _from_package_graph(builder, package_graph, ["modules", "packages"])
    elif key == "repository_layout":
        _from_project_model(builder, project_model, ["workspace_units", "files", "ownership_hints"])
        for item in _as_list(project_model.get("workspace_units"))[:12]:
            builder.add_file_source(_path_from(item), "workspace unit")
    elif key == "package_map":
        _from_package_graph(builder, package_graph, ["modules", "packages", "edges"])
        for item in _as_list(package_graph.get("packages"))[:16]:
            builder.add_file_source(item.get("dir_path"), "package")
    elif key == "entry_points":
        _from_project_model(builder, project_model, ["http_surface", "entry_points", "workspace_units"])
        _from_package_graph(builder, package_graph, ["entrypoint_packages"])
    elif key == "major_flows":
        _from_project_model(builder, project_model, ["http_surface", "integrations", "workspace_units"])
    elif key == "domain_entities":
        _from_config_inventory(builder, config_inventory, ["data_contracts"])
        _from_project_model(builder, project_model, ["important_symbols", "important_packages"])
    elif key == "integrations":
        _from_project_model(builder, project_model, ["integrations", "http_surface"])
        _from_config_inventory(builder, config_inventory, ["api_specs", "dependency_locks"])
    elif key == "configuration":
        _from_config_inventory(
            builder,
            config_inventory,
            ["env_vars", "flags", "config_files", "config_structs", "dependency_locks"],
        )
        for item in _as_list(config_inventory.get("config_files"))[:20]:
            builder.add_file_source(_path_from(item), "config file")
    elif key == "build_run_test":
        _from_project_model(builder, project_model, ["workspace_units", "build", "scripts"])
        for item in _manifest_like_files(project_model)[:20]:
            builder.add_file_source(item, "build/run/test manifest")
    elif key in {"known_gaps", "analysis_limitations"}:
        _from_project_model(builder, project_model, ["diagnostics", "unsupported_patterns", "truncated"])
        _from_config_inventory(builder, config_inventory, ["truncated", "unsupported_patterns"])
    elif key == "change_report":
        _from_commit_log(builder, commit_log, current_file_index)
    elif key == "public_api":
        _from_project_model(builder, project_model, ["go", "code_outline", "workspace_units"])
        _from_package_graph(builder, package_graph, ["modules", "packages"])
    elif key == "command_lifecycle":
        _from_project_model(builder, project_model, ["go", "code_outline", "workspace_units"])
        _from_package_graph(builder, package_graph, ["entrypoint_packages", "packages", "edges"])
    elif key == "flags_and_args":
        _from_config_inventory(builder, config_inventory, ["flags", "config_structs"])
        _from_project_model(builder, project_model, ["go", "code_outline"])
    elif key == "completions":
        _from_project_model(builder, project_model, ["go", "code_outline"])
        _from_package_graph(builder, package_graph, ["packages"])
    elif key == "doc_generation":
        _from_project_model(builder, project_model, ["go", "code_outline", "repository_layout"])
        _from_package_graph(builder, package_graph, ["packages"])
    elif key == "testing":
        _from_project_model(builder, project_model, ["repository_layout", "workspace_units", "go"])
        _from_package_graph(builder, package_graph, ["packages"])
    elif key == "service_map":
        _from_project_model(
            builder,
            project_model,
            ["summary", "repository_layout", "workspace_units", "http_surface", "external_integrations"],
        )
        _from_package_graph(builder, package_graph, ["modules", "packages"])
    elif key == "local_development":
        _from_project_model(builder, project_model, ["repository_layout", "workspace_units", "configuration"])
        _from_config_inventory(builder, config_inventory, ["config_files", "dependency_locks", "env_vars"])
        _add_manifest_sources(builder, project_model, config_inventory)
    elif key == "request_flows":
        _from_project_model(builder, project_model, ["http_surface", "external_integrations", "workspace_units"])
        _from_config_inventory(builder, config_inventory, ["api_specs", "data_contracts"])
    elif key == "data_model":
        _from_config_inventory(builder, config_inventory, ["data_contracts", "config_files"])
        _from_project_model(builder, project_model, ["code_outline", "go"])
    elif key == "api_surface":
        _from_project_model(builder, project_model, ["http_surface", "workspace_units"])
        _from_config_inventory(builder, config_inventory, ["api_specs", "data_contracts"])
    elif key == "frontend":
        _from_project_model(builder, project_model, ["repository_layout", "workspace_units"])
        _from_config_inventory(builder, config_inventory, ["dependency_locks", "config_files"])
    elif key == "deployment":
        _from_project_model(builder, project_model, ["repository_layout", "workspace_units", "configuration"])
        _from_config_inventory(builder, config_inventory, ["config_files", "env_vars", "dependency_locks"])
        _add_manifest_sources(builder, project_model, config_inventory)


def _from_project_model(builder: _SectionBuilder, project_model: dict[str, Any], keys: list[str]) -> None:
    if not project_model:
        return

    builder.add_artifact_source("project_model", ", ".join(keys))
    for key in keys:
        value = project_model.get(key)
        if value is not None:
            builder.evidence[key] = _compact(value)


def _from_package_graph(builder: _SectionBuilder, package_graph: dict[str, Any], keys: list[str]) -> None:
    if not package_graph:
        return

    builder.add_artifact_source("package_graph", ", ".join(keys))
    for key in keys:
        value = package_graph.get(key)
        if value is not None:
            builder.evidence[key] = _compact(value)


def _from_config_inventory(builder: _SectionBuilder, config_inventory: dict[str, Any], keys: list[str]) -> None:
    if not config_inventory:
        return

    builder.add_artifact_source("config_inventory", ", ".join(keys))
    for key in keys:
        value = config_inventory.get(key)
        if value is not None:
            builder.evidence[key] = _compact(value)


def _from_commit_log(
    builder: _SectionBuilder,
    commit_log: dict[str, Any],
    current_file_index: "_CurrentFileIndex",
) -> None:
    if not commit_log:
        return

    builder.add_artifact_source("commit_log", "normalized recent change events")
    summary = commit_log.get("summary")
    if summary is not None:
        builder.evidence["commit_summary"] = _compact(summary)

    change_events = _build_change_events(commit_log, current_file_index)
    if change_events:
        builder.evidence["change_events"] = change_events

    touched_files = _build_touched_file_summary(commit_log, current_file_index)
    if touched_files:
        builder.evidence["touched_file_summary"] = touched_files

    touched_packages = _as_list(commit_log.get("touched_packages"))[:24]
    if touched_packages:
        builder.evidence["touched_package_summary"] = [
            _compact_package_touch(item)
            for item in touched_packages
        ]

    merge_commits = _build_merge_commit_summary(commit_log)
    if merge_commits:
        builder.evidence["merge_commit_summary"] = merge_commits


def _add_retrieval_evidence(builder: _SectionBuilder, retrieval: RetrievalClient) -> None:
    try:
        matches = retrieval.search(
            builder.snapshot_id,
            builder.template.retrieval_query,
            filters=_retrieval_filters(builder.template),
            include_tests=builder.template.retrieval_include_tests,
        )
    except RetrievalClientError as exc:
        builder.evidence["retrieval_error"] = str(exc)
        return

    if not matches:
        return

    filtered_matches = _filter_retrieval_matches(builder.template.key, matches)
    builder.evidence["retrieval_query"] = builder.template.retrieval_query
    builder.evidence["retrieval_matches"] = [
        {
            "chunk_id": match.chunk_id,
            "file_path": match.file_path,
            "symbol_name": match.symbol_name,
            "start_line": match.start_line,
            "end_line": match.end_line,
            "score": match.score,
            "source_kind": match.source_kind,
            "language": match.language,
            "source_scope": match.source_scope,
            "workspace_unit_id": match.workspace_unit_id,
            "package_id": match.package_id,
            "text": match.text,
        }
        for match in filtered_matches[:8]
    ]
    for match in filtered_matches:
        builder.add_retrieved_source(match, builder.template.retrieval_query)


def _retrieval_filters(template: SectionTemplate) -> dict[str, list[str]]:
    return {
        "languages": list(template.retrieval_languages),
        "source_scopes": list(template.retrieval_source_scopes),
        "chunk_kinds": list(template.retrieval_chunk_kinds),
    }


def _should_use_retrieval(section_key: str, existing_sources: list[dict[str, Any]]) -> bool:
    if section_key in {"change_report", "analysis_limitations", "known_gaps"}:
        return False

    if len(existing_sources) < 3:
        return True

    return section_key in {
        "entry_points",
        "public_api",
        "command_lifecycle",
        "flags_and_args",
        "completions",
        "doc_generation",
        "testing",
        "service_map",
        "local_development",
        "request_flows",
        "data_model",
        "api_surface",
        "frontend",
        "deployment",
        "major_flows",
        "domain_entities",
        "build_run_test",
    }


@dataclass(frozen=True)
class _CurrentFileIndex:
    paths: set[str]
    complete: bool

    def state_for(self, path: str | None) -> tuple[bool | None, str]:
        if not path:
            return None, "unknown"
        normalized = _normalize_path(path)
        if normalized in self.paths:
            return True, "present"
        if self.complete:
            return False, "absent"
        return None, "unknown"


def _current_file_index(project_model: dict[str, Any]) -> _CurrentFileIndex:
    paths: set[str] = set()
    complete = False

    files = _as_list(project_model.get("files"))
    if files:
        complete = True
        for item in files:
            path = _path_from(item)
            if path:
                paths.add(_normalize_path(path))

    repository_layout = project_model.get("repository_layout")
    if isinstance(repository_layout, dict):
        for item in _as_list(repository_layout.get("key_files")):
            path = _path_from(item)
            if path:
                paths.add(_normalize_path(path))

    for unit in _as_list(project_model.get("workspace_units")):
        for item in _as_list(unit.get("key_files")):
            path = _path_from(item)
            if path:
                paths.add(_normalize_path(path))
        for path in unit.get("manifest_paths") or []:
            if isinstance(path, str) and path:
                paths.add(_normalize_path(path))

    return _CurrentFileIndex(paths=paths, complete=complete)


def _build_change_events(
    commit_log: dict[str, Any],
    current_file_index: _CurrentFileIndex,
    *,
    limit: int = 80,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for commit in _as_list(commit_log.get("commits")):
        touched_files = _as_list(commit.get("touched_files"))
        for file_record in touched_files:
            path = _path_from(file_record)
            current_file_present, current_file_state = current_file_index.state_for(path)
            events.append(
                {
                    "sha": _optional_str(commit.get("sha")),
                    "short_sha": _optional_str(commit.get("short_sha")),
                    "subject": _optional_str(commit.get("subject")),
                    "is_merge": bool(commit.get("is_merge")),
                    "parents_total": len(commit.get("parents") or []),
                    "path": path,
                    "old_path": _optional_str(file_record.get("old_path")),
                    "status": _optional_str(file_record.get("status")),
                    "change_type": _optional_str(file_record.get("change_type")),
                    "current_file_present": current_file_present,
                    "current_file_state": current_file_state,
                }
            )
            if len(events) >= limit:
                return events
    return events


def _build_touched_file_summary(
    commit_log: dict[str, Any],
    current_file_index: _CurrentFileIndex,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in _as_list(commit_log.get("touched_files"))[:limit]:
        path = _path_from(item)
        current_file_present, current_file_state = current_file_index.state_for(path)
        result.append(
            {
                "path": path,
                "old_paths": item.get("old_paths") or [],
                "commits_total": item.get("commits_total"),
                "latest_commit_sha": _optional_str(item.get("latest_commit_sha")),
                "change_type_counts": item.get("change_type_counts") or {},
                "current_file_present": current_file_present,
                "current_file_state": current_file_state,
            }
        )
    return result


def _compact_package_touch(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "package_id": item.get("package_id"),
        "name": item.get("name"),
        "dir_path": item.get("dir_path"),
        "commits_total": item.get("commits_total"),
        "files_total": item.get("files_total"),
        "change_type_counts": item.get("change_type_counts") or {},
        "touched_files": (item.get("touched_files") or [])[:8],
    }


def _build_merge_commit_summary(
    commit_log: dict[str, Any],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for commit in _as_list(commit_log.get("commits")):
        if not commit.get("is_merge"):
            continue
        result.append(
            {
                "sha": _optional_str(commit.get("sha")),
                "short_sha": _optional_str(commit.get("short_sha")),
                "subject": _optional_str(commit.get("subject")),
                "parents_total": len(commit.get("parents") or []),
                "change_type_counts": commit.get("change_type_counts") or {},
            }
        )
        if len(result) >= limit:
            break
    return result


def _filter_retrieval_matches(
    section_key: str,
    matches: list[RetrievedSource],
) -> list[RetrievedSource]:
    return [
        match
        for match in matches
        if _allow_retrieval_match(section_key, match)
    ]


def _allow_retrieval_match(section_key: str, match: RetrievedSource) -> bool:
    if section_key in {"api_reference"}:
        return True
    if match.source_scope == "generated":
        return False
    if match.source_kind == "generated":
        return False
    if match.file_path and _looks_generated_source_path(match.file_path):
        return False
    if (
        section_key in {"public_api", "command_lifecycle", "flags_and_args", "completions", "package_map"}
        and _looks_consumer_doc_source(match)
    ):
        return False
    return True


def _looks_generated_source_path(path: str) -> bool:
    normalized = _normalize_path(path).lower()
    if normalized.endswith("/docs/docs.go"):
        return True
    return any(part in {".swagger-codegen", "generated"} for part in normalized.split("/"))


def _looks_consumer_doc_source(match: RetrievedSource) -> bool:
    path = _normalize_path(match.file_path or "").lower()
    scope = (match.source_scope or "").lower()
    return (
        scope in {"docs", "documentation"}
        or path.startswith("site/content/")
        or "/examples/" in path
        or "user_guide" in path
    )


def _compact(value: Any, limit: int = 12) -> Any:
    if isinstance(value, list):
        return value[:limit]
    if isinstance(value, dict):
        return {key: _compact(item, limit=limit) for key, item in list(value.items())[:limit]}
    return value


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def _path_from(item: dict[str, Any]) -> str | None:
    for key in ("file_path", "path", "dir_path", "root_path", "manifest_path"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _manifest_like_files(project_model: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for item in _as_list(project_model.get("files")):
        path = _path_from(item)
        if path and path.endswith(("go.mod", "package.json", "pyproject.toml", "Dockerfile", "docker-compose.yml")):
            result.append(path)
    for unit in _as_list(project_model.get("workspace_units")):
        for key in ("manifest_path", "lockfile_path"):
            value = unit.get(key)
            if isinstance(value, str):
                result.append(value)
    return _dedupe(result)


def _add_manifest_sources(
    builder: _SectionBuilder,
    project_model: dict[str, Any],
    config_inventory: dict[str, Any],
) -> None:
    for item in _manifest_like_files(project_model)[:20]:
        builder.add_file_source(item, "development/deployment manifest")
    for item in _as_list(config_inventory.get("config_files"))[:20]:
        builder.add_file_source(_path_from(item), "configuration file")


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _source_kind(value: str | None) -> str:
    if not value:
        return "retrieval_chunk"
    normalized = "".join(
        ch if ("a" <= ch <= "z" or "0" <= ch <= "9") else "_"
        for ch in value.lower()
    ).strip("_")
    return normalized[:64] or "retrieval_chunk"
