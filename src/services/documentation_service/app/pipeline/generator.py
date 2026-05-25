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
    section_spec: dict[str, Any] | None = None


@dataclass(frozen=True)
class GeneratedDocument:
    document_key: str
    title: str
    description: str
    file_name: str
    artifact_kind: str
    section_keys: tuple[str, ...]
    content_markdown: str


@dataclass(frozen=True)
class _DocumentTemplate:
    document_key: str
    title: str
    description: str
    file_name: str
    artifact_kind: str
    section_keys: tuple[str, ...]


class DeveloperHandbookGenerator:
    def assemble_document(self, sections: list[GeneratedSection], *, template_kind: str) -> str:
        documents = self.assemble_documents(sections, template_kind=template_kind)
        return self.assemble_index_document(
            documents,
            sections=sections,
            template_kind=template_kind,
        )

    def assemble_documents(
        self,
        sections: list[GeneratedSection],
        *,
        template_kind: str,
    ) -> list[GeneratedDocument]:
        section_by_key = {section.section_key: section for section in sections}
        documents: list[GeneratedDocument] = []
        for template in _document_templates(template_kind):
            selected_sections = [
                section_by_key[key]
                for key in template.section_keys
                if key in section_by_key
            ]
            if not selected_sections:
                continue

            content = _assemble_document_body(
                title=template.title,
                description=template.description,
                sections=selected_sections,
            )
            documents.append(
                GeneratedDocument(
                    document_key=template.document_key,
                    title=template.title,
                    description=template.description,
                    file_name=template.file_name,
                    artifact_kind=template.artifact_kind,
                    section_keys=tuple(section.section_key for section in selected_sections),
                    content_markdown=content,
                )
            )
        return documents

    def assemble_index_document(
        self,
        documents: list[GeneratedDocument],
        *,
        sections: list[GeneratedSection],
        template_kind: str,
    ) -> str:
        lines = [
            f"# {_document_title(template_kind)}",
            "",
            "This documentation set was generated from indexed repository artifacts and retrieval evidence.",
            "",
            "## Documents",
        ]
        for document in documents:
            lines.append(f"- [{document.title}]({document.file_name}) - {document.description}")

        lines.append("")
        lines.append("## Generated Sections")
        for section in sections:
            document_keys = []
            if section.section_spec:
                document_keys = list(section.section_spec.get("document_keys") or [])
            suffix = f" ({', '.join(document_keys)})" if document_keys else ""
            lines.append(f"- `{section.section_key}` - {section.title}{suffix}")

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
        documents: list[GeneratedDocument],
        document_artifacts: list[dict[str, Any]],
        documentation_artifact: dict[str, Any],
        attempt: int | None = None,
        publication_state: str = "final",
        evidence_pack_artifact: dict[str, Any] | None = None,
        rendered_evidence_pack_artifact: dict[str, Any] | None = None,
        prompt_contract_artifact: dict[str, Any] | None = None,
        verification_summary: dict[str, Any] | None = None,
        verification_report_artifact: dict[str, Any] | None = None,
        repair_summary: dict[str, Any] | None = None,
        repair_plan_artifact: dict[str, Any] | None = None,
        repair_attempts_artifact: dict[str, Any] | None = None,
        pipeline_trace_artifact: dict[str, Any] | None = None,
        draft_manifest_artifact: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": 2,
            "documentation_run_id": documentation_run_id,
            "repository_id": repository_id,
            "snapshot_id": snapshot_id,
            "attempt": attempt,
            "publication_state": publication_state,
            "template_kind": template_kind,
            "requested_template_kind": requested_template_kind or template_kind,
            "artifact_kind": "documentation_manifest",
            "template_selection": template_selection,
            "repository_classification": repository_classification,
            "documents": [
                {
                    "document_key": document.document_key,
                    "title": document.title,
                    "description": document.description,
                    "file_name": document.file_name,
                    "artifact_kind": document.artifact_kind,
                    "section_keys": list(document.section_keys),
                    "artifact": document_artifacts[index],
                }
                for index, document in enumerate(documents)
            ],
            "sections": [
                {
                    "section_key": section.section_key,
                    "title": section.title,
                    "ordinal": section.ordinal,
                    "section_spec": section.section_spec,
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
            "verification_summary": verification_summary,
            "verification_report": verification_report_artifact,
            "repair_summary": repair_summary,
            "repair_plan": repair_plan_artifact,
            "repair_attempts": repair_attempts_artifact,
            "pipeline_trace": pipeline_trace_artifact,
            "draft_manifest": draft_manifest_artifact,
        }


def _assemble_document_body(
    *,
    title: str,
    description: str,
    sections: list[GeneratedSection],
) -> str:
    lines = [
        f"# {title}",
        "",
        description,
        "",
    ]
    for section in sections:
        lines.append(section.content_markdown.rstrip())
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _document_templates(template_kind: str) -> tuple[_DocumentTemplate, ...]:
    if template_kind == "go_library_handbook":
        return (
            _document_template("repository_brief", "Repository Brief", "Short orientation for readers who need a fast understanding of the library.", ("overview",)),
            _document_template("onboarding_guide", "Onboarding Guide", "Practical build, test and contribution starting points.", ("build_run_test", "testing")),
            _document_template("architecture_map", "Architecture Map", "Package structure and command/runtime design.", ("package_map", "public_api", "command_lifecycle", "known_gaps")),
            _document_template("api_reference", "API Reference", "Public Go API surface grounded in indexed symbols.", ("public_api",)),
            _document_template("configuration_reference", "Configuration Reference", "Flags, arguments and configuration-like inputs.", ("flags_and_args",)),
            _document_template("commands_reference", "Commands Reference", "Command lifecycle, flags, completions and docs generation.", ("command_lifecycle", "flags_and_args", "completions", "doc_generation", "build_run_test")),
            _document_template("package_service_index", "Package Index", "Important packages and their responsibilities.", ("package_map",)),
            _document_template("change_report", "Change Report", "Recent history kept separate from current architecture.", ("change_report",)),
        )
    if template_kind == "monorepo_web_app_handbook":
        return (
            _document_template("repository_brief", "Repository Brief", "Short orientation for readers who need a fast understanding of the monorepo.", ("overview",)),
            _document_template("onboarding_guide", "Onboarding Guide", "Local development and setup guidance for contributors.", ("local_development", "configuration")),
            _document_template("architecture_map", "Architecture Map", "Current frontend/backend structure, flows and deployment shape.", ("service_map", "request_flows", "data_model", "frontend", "deployment", "known_gaps")),
            _document_template("api_reference", "API Reference", "HTTP/API surface and request-flow evidence.", ("api_surface", "request_flows")),
            _document_template("configuration_reference", "Configuration Reference", "Environment, config and deployment settings.", ("configuration", "deployment")),
            _document_template("commands_reference", "Commands Reference", "Local scripts, Docker and service commands found in manifests.", ("local_development",)),
            _document_template("package_service_index", "Service Index", "Workspace units, services and frontend areas.", ("service_map", "frontend")),
            _document_template("change_report", "Change Report", "Recent history kept separate from current architecture.", ("change_report",)),
        )
    return (
        _document_template("repository_brief", "Repository Brief", "Short orientation for readers who need a fast understanding of the repository.", ("overview",)),
        _document_template("onboarding_guide", "Onboarding Guide", "Build, run, test and configuration starting points.", ("build_run_test", "configuration")),
        _document_template("architecture_map", "Architecture Map", "Repository structure, package map, entry points and flows.", ("repository_layout", "package_map", "entry_points", "major_flows", "domain_entities", "integrations", "known_gaps")),
        _document_template("api_reference", "API Reference", "Entry points and integration/API evidence.", ("entry_points", "integrations")),
        _document_template("configuration_reference", "Configuration Reference", "Environment variables, config files and dependency settings.", ("configuration",)),
        _document_template("commands_reference", "Commands Reference", "Commands and local development actions supported by evidence.", ("build_run_test", "entry_points")),
        _document_template("package_service_index", "Package And Service Index", "Repository layout and package/service responsibilities.", ("repository_layout", "package_map")),
        _document_template("change_report", "Change Report", "Recent history kept separate from current architecture.", ("change_report",)),
    )


def _document_template(
    document_key: str,
    title: str,
    description: str,
    section_keys: tuple[str, ...],
) -> _DocumentTemplate:
    return _DocumentTemplate(
        document_key=document_key,
        title=title,
        description=description,
        file_name=f"{document_key}.md",
        artifact_kind=f"document_{document_key}",
        section_keys=section_keys,
    )


def _document_title(template_kind: str) -> str:
    return {
        "developer_handbook": "Developer Handbook",
        "go_library_handbook": "Go Library Handbook",
        "monorepo_web_app_handbook": "Monorepo Web App Handbook",
    }.get(template_kind, "Developer Handbook")
