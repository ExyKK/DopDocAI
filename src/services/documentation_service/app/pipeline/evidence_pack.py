import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvidencePackBudget:
    max_tokens: int = 120_000
    max_source_tokens: int = 16_000
    max_sources: int = 80


@dataclass(frozen=True)
class EvidencePackSource:
    source_id: str
    source_kind: str
    selection_reason: str
    content: str
    estimated_tokens: int
    source_ordinal: int | None = None
    file_path: str | None = None
    symbol_name: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    chunk_id: str | None = None
    score: float | None = None
    language: str | None = None
    source_scope: str | None = None
    workspace_unit_id: str | None = None
    package_id: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "source_ordinal": self.source_ordinal,
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "chunk_id": self.chunk_id,
            "score": self.score,
            "language": self.language,
            "source_scope": self.source_scope,
            "workspace_unit_id": self.workspace_unit_id,
            "package_id": self.package_id,
            "selection_reason": self.selection_reason,
            "estimated_tokens": self.estimated_tokens,
            "truncated": self.truncated,
            "content": self.content,
        }


@dataclass(frozen=True)
class OmittedEvidenceSource:
    source_kind: str
    selection_reason: str
    omitted_reason: str
    estimated_tokens: int
    file_path: str | None = None
    symbol_name: str | None = None
    chunk_id: str | None = None
    language: str | None = None
    source_scope: str | None = None
    workspace_unit_id: str | None = None
    package_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "file_path": self.file_path,
            "symbol_name": self.symbol_name,
            "chunk_id": self.chunk_id,
            "language": self.language,
            "source_scope": self.source_scope,
            "workspace_unit_id": self.workspace_unit_id,
            "package_id": self.package_id,
            "selection_reason": self.selection_reason,
            "omitted_reason": self.omitted_reason,
            "estimated_tokens": self.estimated_tokens,
        }


@dataclass(frozen=True)
class EvidencePack:
    schema_version: int
    section_key: str
    title: str
    ordinal: int
    budget: EvidencePackBudget
    estimated_tokens: int
    sources: list[EvidencePackSource]
    omitted_sources: list[OmittedEvidenceSource]
    truncated_sources: list[str]
    retrieval_query: str | None
    retrieval_error: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "section_key": self.section_key,
            "title": self.title,
            "ordinal": self.ordinal,
            "budget": {
                "max_tokens": self.budget.max_tokens,
                "max_source_tokens": self.budget.max_source_tokens,
                "max_sources": self.budget.max_sources,
            },
            "estimated_tokens": self.estimated_tokens,
            "retrieval_query": self.retrieval_query,
            "retrieval_error": self.retrieval_error,
            "sources": [source.to_dict() for source in self.sources],
            "omitted_sources": [source.to_dict() for source in self.omitted_sources],
            "truncated_sources": self.truncated_sources,
        }


def build_evidence_pack(
    *,
    section_key: str,
    title: str,
    ordinal: int,
    evidence: dict[str, Any],
    sources: list[dict[str, Any]],
    budget: EvidencePackBudget,
) -> EvidencePack:
    candidates = _structured_candidates(evidence, sources) + _retrieval_candidates(evidence, sources)
    selected: list[EvidencePackSource] = []
    omitted: list[OmittedEvidenceSource] = []
    truncated_sources: list[str] = []
    used_tokens = 0

    for candidate in candidates:
        if len(selected) >= budget.max_sources:
            omitted.append(_omit(candidate, "max_sources_exceeded"))
            continue

        source = _pack_source(candidate, len(selected) + 1, budget.max_source_tokens)

        if used_tokens + source.estimated_tokens > budget.max_tokens:
            omitted.append(_omit(candidate, "max_tokens_exceeded"))
            continue

        if source.truncated:
            truncated_sources.append(source.source_id)

        used_tokens += source.estimated_tokens
        selected.append(source)

    return EvidencePack(
        schema_version=1,
        section_key=section_key,
        title=title,
        ordinal=ordinal,
        budget=budget,
        estimated_tokens=used_tokens,
        sources=selected,
        omitted_sources=omitted,
        truncated_sources=truncated_sources,
        retrieval_query=_optional_str(evidence.get("retrieval_query")),
        retrieval_error=_optional_str(evidence.get("retrieval_error")),
    )


def build_evidence_pack_manifest(
    *,
    documentation_run_id: str,
    repository_id: str,
    snapshot_id: str,
    template_kind: str,
    packs: list[EvidencePack],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "documentation_run_id": documentation_run_id,
        "repository_id": repository_id,
        "snapshot_id": snapshot_id,
        "template_kind": template_kind,
        "artifact_kind": "evidence_pack_manifest",
        "sections": [pack.to_dict() for pack in packs],
        "summary": {
            "sections_total": len(packs),
            "estimated_tokens_total": sum(pack.estimated_tokens for pack in packs),
            "sources_total": sum(len(pack.sources) for pack in packs),
            "omitted_sources_total": sum(len(pack.omitted_sources) for pack in packs),
            "truncated_sources_total": sum(len(pack.truncated_sources) for pack in packs),
        },
    }


def estimate_tokens(value: str) -> int:
    if not value:
        return 0
    return max(1, (len(value) + 3) // 4)


def _structured_candidates(
    evidence: dict[str, Any],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    artifact_sources = [source for source in sources if source.get("source_kind") == "analysis_artifact"]
    artifact_by_note = {
        str(source.get("note") or "").split(":", 1)[0]: source
        for source in artifact_sources
        if source.get("note")
    }

    for key, value in evidence.items():
        if key in {"retrieval_query", "retrieval_matches", "retrieval_error"}:
            continue

        artifact_kind = _artifact_kind_for_evidence_key(key)
        source = artifact_by_note.get(artifact_kind) or (artifact_sources[0] if artifact_sources else None)
        content = f"{key}:\n{_json(value)}"
        candidates.append(
            {
                "source_kind": "structured_artifact",
                "source": source,
                "selection_reason": f"structured {artifact_kind}.{key}",
                "content": content,
                "file_path": None,
                "symbol_name": None,
                "chunk_id": None,
                "score": None,
            }
        )

    return candidates


def _retrieval_candidates(
    evidence: dict[str, Any],
    sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    retrieval_matches = evidence.get("retrieval_matches")
    if not isinstance(retrieval_matches, list):
        return []

    source_by_chunk = {
        source.get("chunk_id"): source
        for source in sources
        if source.get("chunk_id")
    }
    candidates: list[dict[str, Any]] = []
    for index, match in enumerate(retrieval_matches, start=1):
        if not isinstance(match, dict):
            continue

        chunk_id = match.get("chunk_id")
        source = source_by_chunk.get(chunk_id)
        text = _optional_str(match.get("text")) or _retrieval_metadata(match)
        file_path = _optional_str(match.get("file_path"))
        symbol_name = _optional_str(match.get("symbol_name"))
        candidates.append(
            {
                "source_kind": _optional_str(match.get("source_kind")) or "retrieval_chunk",
                "source": source,
                "selection_reason": f"retrieval rank {index}",
                "content": text,
                "file_path": file_path,
                "symbol_name": symbol_name,
                "start_line": match.get("start_line"),
                "end_line": match.get("end_line"),
                "chunk_id": _optional_str(chunk_id),
                "score": match.get("score"),
                "language": _optional_str(match.get("language")),
                "source_scope": _optional_str(match.get("source_scope")),
                "workspace_unit_id": _optional_str(match.get("workspace_unit_id")),
                "package_id": _optional_str(match.get("package_id")),
            }
        )

    return candidates


def _pack_source(
    candidate: dict[str, Any],
    sequence: int,
    max_source_tokens: int,
) -> EvidencePackSource:
    content = _optional_str(candidate.get("content")) or ""
    estimated = estimate_tokens(content)
    truncated = False
    if estimated > max_source_tokens:
        content = _truncate_to_tokens(content, max_source_tokens)
        estimated = estimate_tokens(content)
        truncated = True

    source = candidate.get("source") if isinstance(candidate.get("source"), dict) else {}
    return EvidencePackSource(
        source_id=f"S{sequence}",
        source_kind=_optional_str(candidate.get("source_kind")) or "evidence",
        source_ordinal=_int_or_none(source.get("ordinal")),
        file_path=_optional_str(candidate.get("file_path")) or _optional_str(source.get("file_path")),
        symbol_name=_optional_str(candidate.get("symbol_name")) or _optional_str(source.get("symbol_name")),
        start_line=_int_or_none(candidate.get("start_line")) or _int_or_none(source.get("start_line")),
        end_line=_int_or_none(candidate.get("end_line")) or _int_or_none(source.get("end_line")),
        chunk_id=_optional_str(candidate.get("chunk_id")) or _optional_str(source.get("chunk_id")),
        score=_float_or_none(candidate.get("score")) or _float_or_none(source.get("score")),
        language=_optional_str(candidate.get("language")) or _optional_str(source.get("language")),
        source_scope=_optional_str(candidate.get("source_scope")) or _optional_str(source.get("source_scope")),
        workspace_unit_id=_optional_str(candidate.get("workspace_unit_id"))
        or _optional_str(source.get("workspace_unit_id")),
        package_id=_optional_str(candidate.get("package_id")) or _optional_str(source.get("package_id")),
        selection_reason=_optional_str(candidate.get("selection_reason")) or "selected evidence",
        estimated_tokens=estimated,
        truncated=truncated,
        content=content,
    )


def _omit(candidate: dict[str, Any], reason: str) -> OmittedEvidenceSource:
    content = _optional_str(candidate.get("content")) or ""
    return OmittedEvidenceSource(
        source_kind=_optional_str(candidate.get("source_kind")) or "evidence",
        file_path=_optional_str(candidate.get("file_path")),
        symbol_name=_optional_str(candidate.get("symbol_name")),
        chunk_id=_optional_str(candidate.get("chunk_id")),
        language=_optional_str(candidate.get("language")),
        source_scope=_optional_str(candidate.get("source_scope")),
        workspace_unit_id=_optional_str(candidate.get("workspace_unit_id")),
        package_id=_optional_str(candidate.get("package_id")),
        selection_reason=_optional_str(candidate.get("selection_reason")) or "candidate evidence",
        omitted_reason=reason,
        estimated_tokens=estimate_tokens(content),
    )


def _artifact_kind_for_evidence_key(key: str) -> str:
    if key in {"modules", "packages", "edges", "entrypoint_packages"}:
        return "package_graph"
    if key in {
        "env_vars",
        "flags",
        "config_files",
        "config_structs",
        "dependency_locks",
        "api_specs",
        "data_contracts",
    }:
        return "config_inventory"
    if key in {
        "change_events",
        "commit_summary",
        "touched_file_summary",
        "touched_package_summary",
        "merge_commit_summary",
        "commits",
        "recent_commits",
        "touched_files",
        "touched_packages",
        "summary",
    }:
        return "commit_log"
    return "project_model"


def _retrieval_metadata(match: dict[str, Any]) -> str:
    fields = {
        "file_path": match.get("file_path"),
        "symbol_name": match.get("symbol_name"),
        "source_kind": match.get("source_kind"),
        "score": match.get("score"),
    }
    return _json({key: value for key, value in fields.items() if value is not None})


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _truncate_to_tokens(value: str, max_tokens: int) -> str:
    suffix = "\n[truncated]"
    max_chars = max(1, max_tokens * 4)
    if len(value) <= max_chars:
        return value
    if max_chars <= len(suffix):
        return suffix.strip()
    return value[: max_chars - len(suffix)].rstrip() + suffix


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
