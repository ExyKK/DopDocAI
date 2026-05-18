import json
from dataclasses import dataclass
from typing import Any

from app.pipeline.evidence import SectionEvidence


@dataclass(frozen=True)
class GeneratedSection:
    section_key: str
    title: str
    ordinal: int
    content_markdown: str
    source_count: int


class DeveloperHandbookGenerator:
    def generate_sections(self, sections: list[SectionEvidence]) -> list[GeneratedSection]:
        return [_generate_section(section) for section in sections]

    def assemble_document(self, sections: list[GeneratedSection]) -> str:
        lines = [
            "# Developer Handbook",
            "",
            "This handbook was generated from indexed repository artifacts and retrieval evidence.",
            "",
            "## Table of Contents",
        ]
        for section in sections:
            lines.append(f"- [{section.title}](#{_anchor(section.title)})")

        lines.append("")
        for section in sections:
            lines.append(section.content_markdown.rstrip())
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def build_manifest(
        self,
        *,
        documentation_run_id: str,
        repository_id: str,
        snapshot_id: str,
        template_kind: str,
        sections: list[GeneratedSection],
        section_artifacts: list[dict[str, Any]],
        documentation_artifact: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "documentation_run_id": documentation_run_id,
            "repository_id": repository_id,
            "snapshot_id": snapshot_id,
            "template_kind": template_kind,
            "artifact_kind": "developer_handbook",
            "sections": [
                {
                    "section_key": section.section_key,
                    "title": section.title,
                    "ordinal": section.ordinal,
                    "source_count": section.source_count,
                    "artifact": section_artifacts[index],
                }
                for index, section in enumerate(sections)
            ],
            "documentation": documentation_artifact,
        }


def _generate_section(section: SectionEvidence) -> GeneratedSection:
    lines = [
        f"## {section.title}",
        "",
        _opening_sentence(section),
        "",
    ]

    summary_lines = _evidence_summary(section.evidence)
    if summary_lines:
        lines.append("### Key Evidence")
        lines.extend(f"- {line}" for line in summary_lines[:10])
        lines.append("")

    if section.sources:
        lines.append("### Sources")
        for source in section.sources[:12]:
            lines.append(f"- [{source['ordinal']}] {_format_source(source)}")
        lines.append("")

    if not summary_lines and not section.sources:
        lines.append("No strong indexed evidence was found for this section yet.")
        lines.append("")

    return GeneratedSection(
        section_key=section.section_key,
        title=section.title,
        ordinal=section.ordinal,
        content_markdown="\n".join(lines).rstrip() + "\n",
        source_count=len(section.sources),
    )


def _opening_sentence(section: SectionEvidence) -> str:
    return {
        "overview": "This section summarizes the repository shape and the highest-signal components found in the indexed artifacts.",
        "repository_layout": "This section describes the repository layout, workspace units, and important directories.",
        "package_map": "This section maps modules and packages using the package graph artifact.",
        "entry_points": "This section lists detected startup paths, command surfaces, and HTTP entry points.",
        "major_flows": "This section captures likely major runtime flows from routes, integrations, and recent change signals.",
        "domain_entities": "This section summarizes domain-like models, data contracts, and important symbols.",
        "integrations": "This section lists detected external APIs, generated specs, dependencies, and service integrations.",
        "configuration": "This section covers environment variables, config files, flags, and operational settings.",
        "build_run_test": "This section collects build, run, and test hints from manifests and workspace metadata.",
        "known_gaps": "This section records gaps, unsupported patterns, truncation signals, and low-confidence areas.",
    }.get(section.section_key, "This section summarizes the available evidence for the repository.")


def _evidence_summary(evidence: dict[str, Any]) -> list[str]:
    result: list[str] = []
    for key, value in evidence.items():
        if key == "retrieval_error":
            result.append(f"Retrieval was unavailable for this section: `{value}`.")
            continue
        if key == "retrieval_query":
            continue

        result.extend(_summarize_value(key, value))
    return result


def _summarize_value(key: str, value: Any) -> list[str]:
    label = key.replace("_", " ")
    if isinstance(value, list):
        if not value:
            return []
        return [f"{label}: {_short_json(item)}" for item in value[:5]]
    if isinstance(value, dict):
        if not value:
            return []
        simple_items = []
        for item_key, item_value in list(value.items())[:6]:
            if isinstance(item_value, (str, int, float, bool)) or item_value is None:
                simple_items.append(f"{item_key}={item_value}")
        if simple_items:
            return [f"{label}: {', '.join(simple_items)}"]
        return [f"{label}: {_short_json(value)}"]
    return [f"{label}: `{value}`"]


def _format_source(source: dict[str, Any]) -> str:
    note = source.get("note") or source.get("source_kind") or "source"
    file_path = source.get("file_path")
    symbol_name = source.get("symbol_name")
    line_span = _line_span(source.get("start_line"), source.get("end_line"))

    if file_path:
        result = f"{file_path}"
        if line_span:
            result += f" {line_span}"
        if symbol_name:
            result += f" `{symbol_name}`"
        return f"{result} - {note}"

    return str(note)


def _line_span(start_line: int | None, end_line: int | None) -> str:
    if start_line is None or end_line is None:
        return ""
    if start_line == end_line:
        return f"line {start_line}"
    return f"lines {start_line}-{end_line}"


def _short_json(value: Any, max_length: int = 220) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    if len(rendered) <= max_length:
        return rendered
    return rendered[: max_length - 3].rstrip() + "..."


def _anchor(value: str) -> str:
    return value.lower().replace(",", "").replace(" ", "-")
