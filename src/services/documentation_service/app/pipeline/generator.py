from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeneratedSection:
    section_key: str
    title: str
    ordinal: int
    content_markdown: str
    source_count: int
    generation: dict[str, Any] | None = None


class DeveloperHandbookGenerator:
    def assemble_document(self, sections: list[GeneratedSection], *, template_kind: str) -> str:
        lines = [
            f"# {_document_title(template_kind)}",
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
        requested_template_kind: str | None = None,
        template_selection: dict[str, Any] | None = None,
        repository_classification: dict[str, Any] | None = None,
        sections: list[GeneratedSection],
        section_artifacts: list[dict[str, Any]],
        documentation_artifact: dict[str, Any],
        evidence_pack_artifact: dict[str, Any] | None = None,
        rendered_evidence_pack_artifact: dict[str, Any] | None = None,
        prompt_contract_artifact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "documentation_run_id": documentation_run_id,
            "repository_id": repository_id,
            "snapshot_id": snapshot_id,
            "template_kind": template_kind,
            "requested_template_kind": requested_template_kind or template_kind,
            "artifact_kind": template_kind,
            "template_selection": template_selection,
            "repository_classification": repository_classification,
            "sections": [
                {
                    "section_key": section.section_key,
                    "title": section.title,
                    "ordinal": section.ordinal,
                    "source_count": section.source_count,
                    "generation": section.generation,
                    "artifact": section_artifacts[index],
                }
                for index, section in enumerate(sections)
            ],
            "documentation": documentation_artifact,
            "evidence_pack_manifest": evidence_pack_artifact,
            "rendered_evidence_pack_manifest": rendered_evidence_pack_artifact,
            "prompt_contract_manifest": prompt_contract_artifact,
        }


def _anchor(value: str) -> str:
    return value.lower().replace(",", "").replace(" ", "-")


def _document_title(template_kind: str) -> str:
    return {
        "developer_handbook": "Developer Handbook",
        "go_library_handbook": "Go Library Handbook",
        "monorepo_web_app_handbook": "Monorepo Web App Handbook",
    }.get(template_kind, "Developer Handbook")
