from dataclasses import dataclass, field
from typing import Any

from app.infra.retrieval_client import RetrievedSource, RetrievalClient, RetrievalClientError
from app.pipeline.templates import SectionTemplate


@dataclass
class SectionEvidence:
    section_key: str
    title: str
    ordinal: int
    status: str
    sources: list[dict[str, Any]]
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_request(self) -> dict[str, Any]:
        return {
            "section_key": self.section_key,
            "title": self.title,
            "ordinal": self.ordinal,
            "status": self.status,
            "sources": self.sources,
        }


class EvidencePlanner:
    def __init__(self, retrieval: RetrievalClient | None):
        self._retrieval = retrieval

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
            sections.append(builder.build())

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
                "note": f"retrieval: {query}",
            }
        )

    def build(self) -> SectionEvidence:
        return SectionEvidence(
            section_key=self.template.key,
            title=self.template.title,
            ordinal=self.ordinal,
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

    key = builder.template.key
    if key == "overview":
        _from_project_model(builder, project_model, ["workspace_units", "important_packages", "integrations"])
        _from_package_graph(builder, package_graph, ["modules", "packages"])
        _from_commit_log(builder, commit_log)
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
        _from_commit_log(builder, commit_log)
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
    elif key == "known_gaps":
        _from_project_model(builder, project_model, ["diagnostics", "unsupported_patterns", "truncated"])
        _from_config_inventory(builder, config_inventory, ["truncated", "unsupported_patterns"])
        _from_commit_log(builder, commit_log)


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


def _from_commit_log(builder: _SectionBuilder, commit_log: dict[str, Any]) -> None:
    if not commit_log:
        return

    builder.add_artifact_source("commit_log", "recent commits and touched areas")
    for key in ("commits", "recent_commits", "touched_files", "touched_packages", "summary"):
        value = commit_log.get(key)
        if value is not None:
            builder.evidence[key] = _compact(value)


def _add_retrieval_evidence(builder: _SectionBuilder, retrieval: RetrievalClient) -> None:
    try:
        matches = retrieval.search(builder.snapshot_id, builder.template.retrieval_query)
    except RetrievalClientError as exc:
        builder.evidence["retrieval_error"] = str(exc)
        return

    if not matches:
        return

    builder.evidence["retrieval_query"] = builder.template.retrieval_query
    builder.evidence["retrieval_matches"] = [
        {
            "file_path": match.file_path,
            "symbol_name": match.symbol_name,
            "score": match.score,
            "source_kind": match.source_kind,
        }
        for match in matches[:8]
    ]
    for match in matches:
        builder.add_retrieved_source(match, builder.template.retrieval_query)


def _should_use_retrieval(section_key: str, existing_sources: list[dict[str, Any]]) -> bool:
    if len(existing_sources) < 3:
        return True

    return section_key in {
        "entry_points",
        "major_flows",
        "domain_entities",
        "build_run_test",
        "known_gaps",
    }


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
