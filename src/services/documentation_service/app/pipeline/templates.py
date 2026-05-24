from dataclasses import dataclass

from app.pipeline.classification import RepositoryClassification

DEVELOPER_HANDBOOK = "developer_handbook"
GO_LIBRARY_HANDBOOK = "go_library_handbook"
MONOREPO_WEB_APP_HANDBOOK = "monorepo_web_app_handbook"


@dataclass(frozen=True)
class SectionTemplate:
    key: str
    title: str
    retrieval_query: str


@dataclass(frozen=True)
class TemplateSelection:
    requested_template_kind: str
    effective_template_kind: str
    selection_mode: str
    reason: str
    supported_template_kinds: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "requested_template_kind": self.requested_template_kind,
            "effective_template_kind": self.effective_template_kind,
            "selection_mode": self.selection_mode,
            "reason": self.reason,
            "supported_template_kinds": list(self.supported_template_kinds),
        }


DEVELOPER_HANDBOOK_SECTIONS: tuple[SectionTemplate, ...] = (
    SectionTemplate(
        "overview",
        "Overview",
        "repository architecture overview main responsibilities modules",
    ),
    SectionTemplate(
        "repository_layout",
        "Repository Layout",
        "repository layout directories workspace units frontend backend infrastructure",
    ),
    SectionTemplate(
        "package_map",
        "Package Map",
        "package module import graph important packages responsibilities",
    ),
    SectionTemplate(
        "entry_points",
        "Entry Points",
        "application entry points command handlers HTTP routes startup",
    ),
    SectionTemplate(
        "major_flows",
        "Major Flows",
        "major business flows request lifecycle service interactions",
    ),
    SectionTemplate(
        "domain_entities",
        "Domain Entities",
        "domain entities data models persistence structures",
    ),
    SectionTemplate(
        "integrations",
        "Integrations",
        "external integrations clients APIs databases queues storage services",
    ),
    SectionTemplate(
        "configuration",
        "Configuration",
        "configuration environment variables config files deployment settings",
    ),
    SectionTemplate(
        "build_run_test",
        "Build, Run, Test",
        "build run test commands scripts local development",
    ),
    SectionTemplate(
        "known_gaps",
        "Known Gaps",
        "unsupported patterns generated files missing documentation known gaps",
    ),
)

GO_LIBRARY_HANDBOOK_SECTIONS: tuple[SectionTemplate, ...] = (
    SectionTemplate(
        "overview",
        "Overview",
        "Go repository overview public purpose packages module responsibilities",
    ),
    SectionTemplate(
        "public_api",
        "Public API",
        "exported Go API public types functions methods command package usage",
    ),
    SectionTemplate(
        "command_lifecycle",
        "Command Lifecycle",
        "cobra command lifecycle Execute AddCommand RunE PreRun args validation",
    ),
    SectionTemplate(
        "flags_and_args",
        "Flags And Args",
        "flags arguments validation pflag cobra command options annotations",
    ),
    SectionTemplate(
        "completions",
        "Completions",
        "shell completion bash zsh fish powershell cobra completion generation",
    ),
    SectionTemplate(
        "doc_generation",
        "Documentation Generation",
        "cobra documentation generation markdown manpages command docs examples",
    ),
    SectionTemplate(
        "testing",
        "Testing",
        "Go tests test helpers command behavior completion tests",
    ),
    SectionTemplate(
        "package_map",
        "Package Map",
        "Go modules packages import graph responsibilities",
    ),
    SectionTemplate(
        "build_run_test",
        "Build, Run, Test",
        "Go build test commands modules scripts local development",
    ),
    SectionTemplate(
        "known_gaps",
        "Known Gaps",
        "unsupported patterns generated files missing documentation known gaps",
    ),
)

MONOREPO_WEB_APP_HANDBOOK_SECTIONS: tuple[SectionTemplate, ...] = (
    SectionTemplate(
        "overview",
        "Overview",
        "monorepo web application overview frontend backend services infrastructure",
    ),
    SectionTemplate(
        "service_map",
        "Service Map",
        "backend services frontend app gateway databases infrastructure workspace units",
    ),
    SectionTemplate(
        "local_development",
        "Local Development",
        "local development docker compose package scripts go modules frontend backend",
    ),
    SectionTemplate(
        "request_flows",
        "Request Flows",
        "HTTP request flows gateway service interactions frontend backend clients",
    ),
    SectionTemplate(
        "data_model",
        "Data Model",
        "data models persistence DTO contracts database tables repository models",
    ),
    SectionTemplate(
        "api_surface",
        "API Surface",
        "HTTP routes OpenAPI Swagger API specs handlers request response contracts",
    ),
    SectionTemplate(
        "frontend",
        "Frontend",
        "frontend app routes components API clients package scripts assets",
    ),
    SectionTemplate(
        "configuration",
        "Configuration",
        "environment variables config files docker compose deployment settings",
    ),
    SectionTemplate(
        "deployment",
        "Deployment",
        "deployment docker compose gitlab ci infrastructure database services",
    ),
    SectionTemplate(
        "known_gaps",
        "Known Gaps",
        "unsupported patterns generated files missing documentation known gaps",
    ),
)

SUPPORTED_TEMPLATE_KINDS = (
    DEVELOPER_HANDBOOK,
    GO_LIBRARY_HANDBOOK,
    MONOREPO_WEB_APP_HANDBOOK,
)


def get_section_templates(template_kind: str) -> tuple[SectionTemplate, ...]:
    if template_kind == DEVELOPER_HANDBOOK:
        return DEVELOPER_HANDBOOK_SECTIONS
    if template_kind == GO_LIBRARY_HANDBOOK:
        return GO_LIBRARY_HANDBOOK_SECTIONS
    if template_kind == MONOREPO_WEB_APP_HANDBOOK:
        return MONOREPO_WEB_APP_HANDBOOK_SECTIONS

    raise ValueError(f"Unsupported documentation template: {template_kind}")


def select_documentation_template(
    requested_template_kind: str,
    classification: RepositoryClassification,
) -> TemplateSelection:
    requested = requested_template_kind.strip().lower() or DEVELOPER_HANDBOOK
    if requested in {GO_LIBRARY_HANDBOOK, MONOREPO_WEB_APP_HANDBOOK}:
        return TemplateSelection(
            requested_template_kind=requested,
            effective_template_kind=requested,
            selection_mode="explicit",
            reason="Typed documentation template was requested explicitly.",
            supported_template_kinds=SUPPORTED_TEMPLATE_KINDS,
        )
    if requested not in {DEVELOPER_HANDBOOK, "auto"}:
        raise ValueError(f"Unsupported documentation template: {requested}")

    repository_kind = classification.repository_kind
    signals = classification.signals
    if repository_kind in {"library", "cli_tool"} and signals.get("has_go"):
        return TemplateSelection(
            requested_template_kind=requested,
            effective_template_kind=GO_LIBRARY_HANDBOOK,
            selection_mode="classified",
            reason=f"Repository classified as {repository_kind} with Go package/API signals.",
            supported_template_kinds=SUPPORTED_TEMPLATE_KINDS,
        )
    if repository_kind == "monorepo_web_app":
        return TemplateSelection(
            requested_template_kind=requested,
            effective_template_kind=MONOREPO_WEB_APP_HANDBOOK,
            selection_mode="classified",
            reason="Repository classified as monorepo_web_app with frontend/backend workspace signals.",
            supported_template_kinds=SUPPORTED_TEMPLATE_KINDS,
        )

    return TemplateSelection(
        requested_template_kind=requested,
        effective_template_kind=DEVELOPER_HANDBOOK,
        selection_mode="fallback",
        reason=f"No specialized template exists yet for repository kind '{repository_kind}'.",
        supported_template_kinds=SUPPORTED_TEMPLATE_KINDS,
    )
