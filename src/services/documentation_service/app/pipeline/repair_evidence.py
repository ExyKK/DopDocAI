import json
from dataclasses import dataclass
from typing import Any

from app.infra.retrieval_client import RetrievalClient, RetrievalClientError, RetrievedSource
from app.pipeline.prompt_contract import PromptMessage, SectionPromptContract
from app.pipeline.repair import RepairPlan, finding_requires_targeted_retrieval
from app.pipeline.verification import VerificationFinding

REPAIR_EVIDENCE_DELTA_SCHEMA_VERSION = 1
_MAX_QUERY_LENGTH = 520
_MAX_QUERIES_PER_SECTION = 4
_MAX_DELTA_SOURCES_PER_SECTION = 3
_MAX_DELTA_SOURCES_PER_FINDING = 1
_MAX_NEIGHBORHOOD_LOOKUPS_PER_SECTION = 1
_MAX_DELTA_SOURCE_CHARS = 2600


@dataclass(frozen=True)
class RepairEvidenceDeltaResult:
    updated_contracts: dict[str, SectionPromptContract]
    prompt_deltas: dict[str, dict[str, Any]]
    manifest: dict[str, Any]


def build_repair_evidence_delta(
    *,
    documentation_run_id: str,
    repository_id: str,
    snapshot_id: str,
    template_kind: str,
    repair_plan: RepairPlan,
    contracts_by_section: dict[str, SectionPromptContract],
    retrieval: RetrievalClient | None,
) -> RepairEvidenceDeltaResult:
    updated_contracts: dict[str, SectionPromptContract] = {}
    prompt_deltas: dict[str, dict[str, Any]] = {}
    section_entries: list[dict[str, Any]] = []

    for section_plan in repair_plan.sections:
        contract = contracts_by_section.get(section_plan.section_key)
        if contract is None:
            continue

        section_entry = _expand_section(
            snapshot_id=snapshot_id,
            template_kind=template_kind,
            repair_round=repair_plan.repair_round,
            contract=contract,
            findings=section_plan.findings,
            retrieval=retrieval,
        )
        section_entries.append(section_entry.manifest_entry)
        if section_entry.prompt_delta:
            prompt_deltas[contract.section_key] = section_entry.prompt_delta
        if section_entry.updated_contract is not contract:
            updated_contracts[contract.section_key] = section_entry.updated_contract

    manifest = {
        "schema_version": REPAIR_EVIDENCE_DELTA_SCHEMA_VERSION,
        "artifact_kind": "repair_evidence_delta",
        "documentation_run_id": documentation_run_id,
        "repository_id": repository_id,
        "snapshot_id": snapshot_id,
        "template_kind": template_kind,
        "repair_round": repair_plan.repair_round,
        "retrieval_available": retrieval is not None,
        "sections": section_entries,
        "summary": {
            "sections_total": len(section_entries),
            "findings_requesting_retrieval_total": sum(
                section["summary"]["findings_requesting_retrieval_total"]
                for section in section_entries
            ),
            "queries_total": sum(section["summary"]["queries_total"] for section in section_entries),
            "sources_added_total": sum(
                section["summary"]["sources_added_total"] for section in section_entries
            ),
            "sections_with_delta_sources_total": sum(
                1 for section in section_entries if section["summary"]["sources_added_total"] > 0
            ),
        },
    }
    return RepairEvidenceDeltaResult(
        updated_contracts=updated_contracts,
        prompt_deltas=prompt_deltas,
        manifest=manifest,
    )


@dataclass(frozen=True)
class _SectionExpansion:
    updated_contract: SectionPromptContract
    prompt_delta: dict[str, Any] | None
    manifest_entry: dict[str, Any]


def _expand_section(
    *,
    snapshot_id: str,
    template_kind: str,
    repair_round: int,
    contract: SectionPromptContract,
    findings: list[VerificationFinding],
    retrieval: RetrievalClient | None,
) -> _SectionExpansion:
    next_source_number = _next_source_number(contract.source_ids)
    added_sources: list[dict[str, Any]] = []
    prompt_sources: list[dict[str, Any]] = []
    source_index: list[dict[str, Any]] = []
    finding_entries: list[dict[str, Any]] = []
    seen_sources = _existing_source_keys(contract)
    queries_used = 0
    neighborhood_lookups_used = 0

    for finding in findings:
        decision = _finding_decision(finding)
        if not decision["requests_retrieval"]:
            finding_entries.append(
                {
                    "finding": finding.to_dict(),
                    "retrieval_policy": decision["retrieval_policy"],
                    "status": decision["status"],
                    "reason": decision["reason"],
                    "queries": [],
                    "added_source_ids": [],
                }
            )
            continue
        if len(added_sources) >= _MAX_DELTA_SOURCES_PER_SECTION:
            finding_entries.append(
                {
                    "finding": finding.to_dict(),
                    "retrieval_policy": decision["retrieval_policy"],
                    "status": "skipped",
                    "reason": "section_delta_source_cap_reached",
                    "queries": [],
                    "added_source_ids": [],
                    "discarded_results": [],
                }
            )
            continue
        if retrieval is None:
            finding_entries.append(
                {
                    "finding": finding.to_dict(),
                    "retrieval_policy": "targeted",
                    "status": "skipped",
                    "reason": "retrieval_client_unavailable",
                    "queries": [],
                    "added_source_ids": [],
                    "discarded_results": [],
                }
            )
            continue
        if queries_used >= _MAX_QUERIES_PER_SECTION:
            finding_entries.append(
                {
                    "finding": finding.to_dict(),
                    "retrieval_policy": "targeted",
                    "status": "skipped",
                    "reason": "section_query_cap_reached",
                    "queries": [],
                    "added_source_ids": [],
                    "discarded_results": [],
                }
            )
            continue

        query = _targeted_query(contract, finding, template_kind=template_kind)
        filters, include_tests = _targeted_filters(contract, finding)
        queries: list[dict[str, Any]] = []
        added_for_finding: list[str] = []
        discarded_results: list[dict[str, Any]] = []
        try:
            matches = retrieval.search(
                snapshot_id,
                query,
                top_k=3,
                filters=filters,
                include_tests=include_tests,
            )
            queries_used += 1
            queries.append(
                {
                    "query_kind": "targeted",
                    "query": query,
                    "filters": {**filters, "include_tests": include_tests},
                    "matches_total": len(matches),
                    "error": None,
                }
            )
        except RetrievalClientError as exc:
            finding_entries.append(
                {
                    "finding": finding.to_dict(),
                    "retrieval_policy": "targeted",
                    "status": "retrieval_failed",
                    "reason": str(exc),
                    "queries": [
                        {
                            "query_kind": "targeted",
                            "query": query,
                            "filters": {**filters, "include_tests": include_tests},
                            "matches_total": 0,
                            "error": str(exc),
                        }
                    ],
                    "added_source_ids": [],
                    "discarded_results": [],
                }
            )
            continue

        selected: list[RetrievedSource] = []
        for match in matches:
            discard_reason = _discard_reason(contract, finding, match, seen_sources)
            if discard_reason is not None:
                discarded_results.append(_discarded_result(match, discard_reason))
                continue
            selected.append(match)
            if len(selected) >= _MAX_DELTA_SOURCES_PER_FINDING:
                break

        if (
            selected
            and _allow_neighborhood_lookup(finding)
            and neighborhood_lookups_used < _MAX_NEIGHBORHOOD_LOOKUPS_PER_SECTION
            and queries_used < _MAX_QUERIES_PER_SECTION
            and len(added_sources) + len(selected) < _MAX_DELTA_SOURCES_PER_SECTION
        ):
            neighborhood, used_lookup = _neighborhood_matches(
                retrieval=retrieval,
                snapshot_id=snapshot_id,
                query=query,
                filters=filters,
                include_tests=include_tests,
                seeds=selected[:1],
                seen_sources=seen_sources,
                contract=contract,
                finding=finding,
                queries=queries,
                max_results=max(
                    0,
                    min(
                        _MAX_DELTA_SOURCES_PER_FINDING,
                        _MAX_DELTA_SOURCES_PER_SECTION - len(added_sources) - len(selected),
                    ),
                ),
            )
            selected.extend(neighborhood)
            if used_lookup:
                neighborhood_lookups_used += 1
                queries_used += 1

        for match in selected:
            if len(added_sources) >= _MAX_DELTA_SOURCES_PER_SECTION:
                break
            key = _source_key(match)
            if key in seen_sources:
                continue
            seen_sources.add(key)
            source_id = f"S{next_source_number}"
            next_source_number += 1
            prompt_source, index_item, manifest_source = _source_payload(source_id, match, finding)
            prompt_sources.append(prompt_source)
            source_index.append(index_item)
            added_sources.append(manifest_source)
            added_for_finding.append(source_id)

        finding_entries.append(
            {
                "finding": finding.to_dict(),
                "retrieval_policy": "targeted",
                "status": "sources_added" if added_for_finding else "evidence_not_found",
                "reason": None if added_for_finding else "no_matching_runtime_evidence",
                "queries": queries,
                "added_source_ids": added_for_finding,
                "discarded_results": discarded_results[:8],
            }
        )

    prompt_delta = None
    updated_contract = contract
    if prompt_sources:
        prompt_delta = {
            "schema_version": REPAIR_EVIDENCE_DELTA_SCHEMA_VERSION,
            "repair_round": repair_round,
            "section_key": contract.section_key,
            "instruction": (
                "Use these delta sources only when they directly support a repair. "
                "Do not use them to justify contradicted or wrong-scope claims."
            ),
            "sources": prompt_sources,
            "source_index": source_index,
            "finding_results": finding_entries,
        }
        updated_contract = _extend_contract(contract, prompt_delta)

    manifest_entry = {
        "section_key": contract.section_key,
        "repair_round": repair_round,
        "findings": finding_entries,
        "added_sources": added_sources,
        "summary": {
            "findings_total": len(findings),
            "findings_requesting_retrieval_total": sum(
                1 for finding in findings if finding_requires_targeted_retrieval(finding)
            ),
            "queries_total": sum(len(entry["queries"]) for entry in finding_entries),
            "sources_added_total": len(added_sources),
            "budget": {
                "max_queries_per_section": _MAX_QUERIES_PER_SECTION,
                "max_delta_sources_per_section": _MAX_DELTA_SOURCES_PER_SECTION,
                "max_delta_sources_per_finding": _MAX_DELTA_SOURCES_PER_FINDING,
                "max_neighborhood_lookups_per_section": _MAX_NEIGHBORHOOD_LOOKUPS_PER_SECTION,
                "max_delta_source_chars": _MAX_DELTA_SOURCE_CHARS,
                "queries_used": queries_used,
                "neighborhood_lookups_used": neighborhood_lookups_used,
            },
        },
    }
    return _SectionExpansion(
        updated_contract=updated_contract,
        prompt_delta=prompt_delta,
        manifest_entry=manifest_entry,
    )


def _finding_decision(finding: VerificationFinding) -> dict[str, Any]:
    if finding.section_key in {"known_gaps", "analysis_limitations"}:
        return {
            "requests_retrieval": False,
            "retrieval_policy": "not_needed",
            "status": "skipped",
            "reason": "analysis_limitations_are_rewrite_only",
        }
    if finding.repair_strategy == "remove_claim":
        return {
            "requests_retrieval": False,
            "retrieval_policy": "not_needed",
            "status": "skipped",
            "reason": "remove_claim_does_not_need_retrieval",
        }
    if finding.category in {"contradicted_claim", "wrong_scope"}:
        return {
            "requests_retrieval": False,
            "retrieval_policy": "blocked",
            "status": "skipped",
            "reason": "contradicted_or_wrong_scope_claim_must_be_removed_not_justified",
        }
    if finding.category in {"citation_integrity", "output_hygiene", "readability", "duplication"}:
        return {
            "requests_retrieval": False,
            "retrieval_policy": "not_needed",
            "status": "skipped",
            "reason": "finding_can_be_fixed_by_rewrite_existing_evidence",
        }
    if finding_requires_targeted_retrieval(finding):
        return {
            "requests_retrieval": True,
            "retrieval_policy": "targeted",
            "status": "pending",
            "reason": None,
        }
    return {
        "requests_retrieval": False,
        "retrieval_policy": "not_needed",
        "status": "skipped",
        "reason": "finding_does_not_indicate_missing_evidence",
    }


def _targeted_query(
    contract: SectionPromptContract,
    finding: VerificationFinding,
    *,
    template_kind: str,
) -> str:
    section_spec = contract.section_spec or {}
    pieces = [
        template_kind,
        contract.title,
        finding.claim,
        finding.evidence_needed,
        " ".join(finding.retrieval_hints),
        " ".join(str(item) for item in (section_spec.get("must_cover") or [])[:3]),
    ]
    query = " ".join(piece.strip() for piece in pieces if isinstance(piece, str) and piece.strip())
    return _truncate(query, _MAX_QUERY_LENGTH)


def _targeted_filters(
    contract: SectionPromptContract,
    finding: VerificationFinding,
) -> tuple[dict[str, list[str]], bool]:
    languages = _single_or_empty(_values_from_source_index(contract.source_index, "language"))
    scopes = _single_or_empty(_values_from_source_index(contract.source_index, "source_scope"))
    workspace_unit_ids = _single_or_empty(_values_from_source_index(contract.source_index, "workspace_unit_id"))
    package_ids = _single_or_empty(_values_from_source_index(contract.source_index, "package_id"))
    section_scope = contract.section_spec.get("retrieval_scope") if isinstance(contract.section_spec, dict) else {}
    explicit_languages = False
    explicit_scopes = False
    if isinstance(section_scope, dict):
        explicit_languages = bool(_string_list(section_scope.get("languages")))
        explicit_scopes = bool(_string_list(section_scope.get("source_scopes")))
        languages = _string_list(section_scope.get("languages")) or languages
        scopes = _string_list(section_scope.get("source_scopes")) or scopes
        chunk_kinds = _string_list(section_scope.get("chunk_kinds"))
    else:
        chunk_kinds = []

    include_tests = _finding_mentions_tests(finding) or contract.section_key == "testing"
    if isinstance(section_scope, dict) and isinstance(section_scope.get("include_tests"), bool):
        include_tests = bool(section_scope["include_tests"]) or include_tests
    if contract.template_kind == "go_library_handbook":
        if contract.section_key != "build_run_test":
            languages = ["go"]
        else:
            if not explicit_languages:
                languages = []
            if not explicit_scopes:
                scopes = []
        if contract.section_key in {
            "overview",
            "public_api",
            "command_lifecycle",
            "flags_and_args",
            "completions",
            "package_map",
        }:
            scopes = ["runtime"]
            include_tests = False
        elif contract.section_key == "testing":
            scopes = ["runtime", "test"]
            include_tests = True

    return (
        {
            "workspace_unit_ids": workspace_unit_ids,
            "languages": languages,
            "source_scopes": scopes,
            "chunk_kinds": chunk_kinds,
            "package_ids": package_ids,
            "file_paths": _file_path_hints(finding),
        },
        include_tests,
    )


def _neighborhood_matches(
    *,
    retrieval: RetrievalClient,
    snapshot_id: str,
    query: str,
    filters: dict[str, list[str]],
    include_tests: bool,
    seeds: list[RetrievedSource],
    seen_sources: set[tuple[Any, ...]],
    contract: SectionPromptContract,
    finding: VerificationFinding,
    queries: list[dict[str, Any]],
    max_results: int,
) -> tuple[list[RetrievedSource], bool]:
    result: list[RetrievedSource] = []
    used_lookup = False
    if max_results <= 0:
        return result, used_lookup
    for seed in seeds:
        if not seed.file_path:
            continue
        neighborhood_filters = {
            **filters,
            "file_paths": [seed.file_path],
        }
        neighborhood_query = " ".join(
            item for item in [query, seed.file_path, seed.symbol_name] if item
        )
        try:
            matches = retrieval.search(
                snapshot_id,
                _truncate(neighborhood_query, _MAX_QUERY_LENGTH),
                top_k=2,
                filters=neighborhood_filters,
                include_tests=include_tests,
            )
        except RetrievalClientError as exc:
            queries.append(
                {
                    "query_kind": "source_neighborhood",
                    "query": neighborhood_query,
                    "filters": {**neighborhood_filters, "include_tests": include_tests},
                    "matches_total": 0,
                    "error": str(exc),
                }
            )
            continue

        used_lookup = True
        queries.append(
            {
                "query_kind": "source_neighborhood",
                "query": neighborhood_query,
                "filters": {**neighborhood_filters, "include_tests": include_tests},
                "matches_total": len(matches),
                "error": None,
            }
        )
        for match in matches:
            key = _source_key(match)
            if key in seen_sources:
                continue
            if not _allow_delta_match(contract, finding, match):
                continue
            result.append(match)
            if len(result) >= max_results:
                return result, used_lookup
    return result, used_lookup


def _source_payload(
    source_id: str,
    match: RetrievedSource,
    finding: VerificationFinding,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    content = _render_delta_source(match)
    title = _source_title(match)
    prompt_source = {
        "source_id": source_id,
        "title": title,
        "source_kind": match.source_kind,
        "file_path": match.file_path,
        "symbol_name": match.symbol_name,
        "line_range": _line_range(match.start_line, match.end_line),
        "source_scope": match.source_scope,
        "workspace_unit_id": match.workspace_unit_id,
        "package_id": match.package_id,
        "content_markdown": content,
        "delta_reason": finding.message,
    }
    index_item = {
        "source_id": source_id,
        "title": title,
        "source_kind": match.source_kind,
        "file_path": match.file_path,
        "symbol_name": match.symbol_name,
        "start_line": match.start_line,
        "end_line": match.end_line,
        "chunk_id": match.chunk_id,
        "score": match.score,
        "language": match.language,
        "source_scope": match.source_scope,
        "workspace_unit_id": match.workspace_unit_id,
        "package_id": match.package_id,
    }
    manifest_source = {
        **index_item,
        "content_excerpt": _truncate(match.text, 1200),
    }
    return prompt_source, index_item, manifest_source


def _extend_contract(
    contract: SectionPromptContract,
    prompt_delta: dict[str, Any],
) -> SectionPromptContract:
    prompt_sources = prompt_delta.get("sources") if isinstance(prompt_delta.get("sources"), list) else []
    source_index = prompt_delta.get("source_index") if isinstance(prompt_delta.get("source_index"), list) else []
    added_ids = [
        source.get("source_id")
        for source in prompt_sources
        if isinstance(source, dict) and isinstance(source.get("source_id"), str)
    ]
    prompt_payload = _json_object(contract.messages[-1].content)
    evidence_pack = prompt_payload.setdefault("evidence_pack", {})
    if isinstance(evidence_pack, dict):
        evidence_pack["source_ids"] = [*contract.source_ids, *added_ids]
        evidence_pack.setdefault("sources", [])
        if isinstance(evidence_pack["sources"], list):
            evidence_pack["sources"].extend(prompt_sources)
        evidence_pack.setdefault("source_index", [])
        if isinstance(evidence_pack["source_index"], list):
            evidence_pack["source_index"].extend(source_index)
        evidence_pack.setdefault("repair_evidence_deltas", [])
        if isinstance(evidence_pack["repair_evidence_deltas"], list):
            evidence_pack["repair_evidence_deltas"].append(
                {
                    "schema_version": prompt_delta["schema_version"],
                    "repair_round": prompt_delta["repair_round"],
                    "section_key": prompt_delta["section_key"],
                    "source_ids": added_ids,
                    "finding_results": prompt_delta.get("finding_results") or [],
                }
            )
    citation_rules = prompt_payload.setdefault("citation_rules", {})
    if isinstance(citation_rules, dict):
        citation_rules["allowed_source_ids"] = [*contract.source_ids, *added_ids]

    messages = [
        *contract.messages[:-1],
        PromptMessage(
            role=contract.messages[-1].role,
            content=json.dumps(prompt_payload, ensure_ascii=False, sort_keys=True, indent=2, default=str),
        ),
    ]
    return SectionPromptContract(
        schema_version=contract.schema_version,
        template_kind=contract.template_kind,
        section_key=contract.section_key,
        title=contract.title,
        ordinal=contract.ordinal,
        section_spec=contract.section_spec,
        output_language=contract.output_language,
        messages=messages,
        source_ids=[*contract.source_ids, *added_ids],
        source_index=[*contract.source_index, *source_index],
        estimated_input_tokens=contract.estimated_input_tokens
        + sum(_estimate_tokens(source.get("content_markdown")) for source in prompt_sources),
    )


def _allow_delta_match(
    contract: SectionPromptContract,
    finding: VerificationFinding,
    match: RetrievedSource,
) -> bool:
    if match.source_scope == "generated" or match.source_kind == "generated":
        return False
    if match.file_path and _looks_generated_path(match.file_path):
        return False
    if finding.category in {"contradicted_claim", "wrong_scope"}:
        return False
    if contract.section_key == "build_run_test" and match.source_kind == "go_symbol":
        return False
    if (
        contract.template_kind == "go_library_handbook"
        and contract.section_key in {"overview", "public_api", "command_lifecycle", "flags_and_args"}
        and _looks_consumer_doc(match)
    ):
        return False
    return True


def _discard_reason(
    contract: SectionPromptContract,
    finding: VerificationFinding,
    match: RetrievedSource,
    seen_sources: set[tuple[Any, ...]],
) -> str | None:
    if _source_key(match) in seen_sources:
        return "duplicate_source"
    if not _allow_delta_match(contract, finding, match):
        return "disallowed_by_section_policy"
    return None


def _discarded_result(match: RetrievedSource, reason: str) -> dict[str, Any]:
    return {
        "reason": reason,
        "chunk_id": match.chunk_id,
        "file_path": match.file_path,
        "symbol_name": match.symbol_name,
        "source_kind": match.source_kind,
        "language": match.language,
        "source_scope": match.source_scope,
        "score": match.score,
    }


def _values_from_source_index(source_index: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for source in source_index:
        value = source.get(key)
        if isinstance(value, str) and value and value not in values:
            values.append(value)
    return values


def _single_or_empty(values: list[str]) -> list[str]:
    if len(values) == 1:
        return values
    return []


def _finding_mentions_tests(finding: VerificationFinding) -> bool:
    text = " ".join(
        item
        for item in [
            finding.claim,
            finding.evidence_needed,
            finding.message,
            finding.suggested_fix,
        ]
        if item
    ).lower()
    return any(marker in text for marker in ("test", "_test", "тест"))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _file_path_hints(finding: VerificationFinding) -> list[str]:
    text = " ".join(
        item
        for item in [
            finding.claim,
            finding.evidence_needed,
            finding.message,
            finding.suggested_fix,
            " ".join(finding.retrieval_hints),
        ]
        if item
    )
    hints: list[str] = []
    for token in text.replace("`", " ").replace(",", " ").split():
        normalized = token.strip("()[]{}:;\"'")
        if not normalized:
            continue
        if "/" in normalized or normalized.endswith(
            (
                ".go",
                ".mod",
                ".sum",
                ".yml",
                ".yaml",
                ".json",
                ".toml",
                ".sql",
                ".md",
            )
        ) or normalized in {"Makefile", "Dockerfile"}:
            hints.append(normalized)
    return _dedupe(hints)[:4]


def _allow_neighborhood_lookup(finding: VerificationFinding) -> bool:
    if _file_path_hints(finding):
        return True
    for hint in finding.retrieval_hints:
        if "/" in hint or "::" in hint or hint.startswith("S") and hint[1:].isdigit():
            return True
        if "." in hint and " " not in hint:
            return True
    return False


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _existing_source_keys(contract: SectionPromptContract) -> set[tuple[Any, ...]]:
    result: set[tuple[Any, ...]] = set()
    for source in contract.source_index:
        result.add(
            (
                source.get("chunk_id"),
                source.get("file_path"),
                source.get("symbol_name"),
                source.get("start_line"),
                source.get("end_line"),
            )
        )
    return result


def _source_key(match: RetrievedSource) -> tuple[Any, ...]:
    return (
        match.chunk_id,
        match.file_path,
        match.symbol_name,
        match.start_line,
        match.end_line,
    )


def _next_source_number(source_ids: list[str]) -> int:
    numbers = []
    for source_id in source_ids:
        if source_id.startswith("S") and source_id[1:].isdigit():
            numbers.append(int(source_id[1:]))
    return (max(numbers) if numbers else len(source_ids)) + 1


def _source_title(match: RetrievedSource) -> str:
    if match.symbol_name and match.file_path:
        return f"{match.symbol_name} ({match.file_path})"
    if match.file_path:
        return match.file_path
    return match.symbol_name or match.chunk_id or "retrieved source"


def _render_delta_source(match: RetrievedSource) -> str:
    lines = [
        f"Retrieved source: `{_source_title(match)}`",
        f"- kind: `{match.source_kind}`",
    ]
    if match.language:
        lines.append(f"- language: `{match.language}`")
    if match.source_scope:
        lines.append(f"- source_scope: `{match.source_scope}`")
    if match.start_line or match.end_line:
        lines.append(f"- lines: `{_line_range(match.start_line, match.end_line)}`")
    lines.extend(["", "Excerpt:", "", _truncate(match.text, _MAX_DELTA_SOURCE_CHARS)])
    return "\n".join(lines).strip()


def _line_range(start_line: int | None, end_line: int | None) -> str | None:
    if start_line and end_line:
        return f"{start_line}-{end_line}"
    if start_line:
        return str(start_line)
    return None


def _looks_generated_path(path: str) -> bool:
    normalized = path.strip().replace("\\", "/").lower()
    if normalized.endswith("/docs/docs.go"):
        return True
    return any(part in {".swagger-codegen", "generated"} for part in normalized.split("/"))


def _looks_consumer_doc(match: RetrievedSource) -> bool:
    path = (match.file_path or "").strip().replace("\\", "/").lower()
    scope = (match.source_scope or "").lower()
    return (
        scope in {"docs", "documentation"}
        or path.startswith("site/content/")
        or "/examples/" in path
        or "user_guide" in path
    )


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _estimate_tokens(value: Any) -> int:
    text = str(value or "")
    return max(1, (len(text) + 3) // 4) if text else 0


def _truncate(value: str | None, max_length: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_length:
        return text
    return text[: max(0, max_length - 14)].rstrip() + "\n[truncated]"
