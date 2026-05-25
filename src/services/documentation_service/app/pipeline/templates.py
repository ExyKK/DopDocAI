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
    purpose: str = ""
    must_cover: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    output_style: str | None = None
    document_keys: tuple[str, ...] = ()
    retrieval_languages: tuple[str, ...] = ()
    retrieval_source_scopes: tuple[str, ...] = ()
    retrieval_chunk_kinds: tuple[str, ...] = ()
    retrieval_include_tests: bool | None = None

    def to_prompt_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "title": self.title,
            "purpose": self.purpose,
            "must_cover": list(self.must_cover),
            "avoid": list(self.avoid),
            "output_style": self.output_style,
            "document_keys": list(self.document_keys),
            "retrieval_scope": {
                "languages": list(self.retrieval_languages),
                "source_scopes": list(self.retrieval_source_scopes),
                "chunk_kinds": list(self.retrieval_chunk_kinds),
                "include_tests": self.retrieval_include_tests,
            },
        }


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
        purpose="Give a short current-state orientation for a developer opening the repository.",
        must_cover=(
            "what the repository appears to contain now",
            "main runtime responsibilities",
            "most important components or workspace units",
        ),
        avoid=(
            "detailed file inventory",
            "claims based only on commit history",
        ),
        output_style="2-4 short paragraphs plus a compact bullet list when useful.",
        document_keys=("repository_brief",),
    ),
    SectionTemplate(
        "repository_layout",
        "Repository Layout",
        "repository layout directories workspace units frontend backend infrastructure",
        purpose="Explain how the repository is physically organized.",
        must_cover=("top-level areas", "workspace units", "ownership hints"),
        avoid=("listing every file",),
        document_keys=("architecture_map", "package_service_index"),
    ),
    SectionTemplate(
        "package_map",
        "Package Map",
        "package module import graph important packages responsibilities",
        purpose="Map packages or modules to responsibilities.",
        must_cover=("important packages", "module boundaries", "notable dependencies"),
        avoid=("raw import graph dumps",),
        document_keys=("architecture_map", "package_service_index"),
    ),
    SectionTemplate(
        "entry_points",
        "Entry Points",
        "application entry points command handlers HTTP routes startup",
        purpose="Show where execution starts and which handlers or commands are externally reachable.",
        must_cover=("startup paths", "handlers or commands", "route-like entry points when present"),
        avoid=("inventing missing APIs",),
        document_keys=("architecture_map", "api_reference", "commands_reference"),
    ),
    SectionTemplate(
        "major_flows",
        "Major Flows",
        "major business flows request lifecycle service interactions",
        purpose="Describe runtime flows visible from handlers, integrations and workspace boundaries.",
        must_cover=("request or command lifecycle", "cross-component calls", "external integrations"),
        avoid=("using recent commits as architecture facts",),
        document_keys=("architecture_map",),
    ),
    SectionTemplate(
        "domain_entities",
        "Domain Entities",
        "domain entities data models persistence structures",
        purpose="Summarize domain/data structures that shape the application.",
        must_cover=("important models/contracts", "persistence-facing structures", "ownership by package or service"),
        avoid=("unbounded schema dumps",),
        document_keys=("architecture_map",),
    ),
    SectionTemplate(
        "integrations",
        "Integrations",
        "external integrations clients APIs databases queues storage services",
        purpose="List external systems and integration boundaries supported by evidence.",
        must_cover=("databases/services/clients", "API specs when present", "where integrations are configured"),
        avoid=("guessing deployment topology",),
        document_keys=("architecture_map", "api_reference"),
    ),
    SectionTemplate(
        "configuration",
        "Configuration",
        "configuration environment variables config files deployment settings",
        purpose="Explain runtime and development configuration.",
        must_cover=("environment variables", "config files", "dependency or deployment manifests"),
        avoid=("secret values", "raw config dumps"),
        document_keys=("onboarding_guide", "configuration_reference"),
    ),
    SectionTemplate(
        "build_run_test",
        "Build, Run, Test",
        "build run test commands scripts local development",
        purpose="Tell a developer how to build, run and test the project from available manifests.",
        must_cover=("build commands", "run/dev commands", "test commands or missing evidence"),
        avoid=("commands not supported by evidence",),
        document_keys=("onboarding_guide", "commands_reference"),
    ),
    SectionTemplate(
        "known_gaps",
        "Known Gaps",
        "unsupported patterns generated files missing documentation known gaps",
        purpose="Record limits of the generated analysis and weak evidence areas.",
        must_cover=("unsupported patterns", "generated/truncated inputs", "missing evidence"),
        avoid=("treating historical commits as current bugs",),
        document_keys=("architecture_map",),
    ),
    SectionTemplate(
        "change_report",
        "Change Report",
        "recent commit history change events touched files packages merge commits",
        purpose="Summarize recent repository history separately from current architecture.",
        must_cover=("recent change themes", "touched files/packages", "merge-heavy or noisy history"),
        avoid=("claiming current file absence from historical deletions alone",),
        output_style="Separate current-state caveats from historical observations.",
        document_keys=("change_report",),
    ),
)

GO_LIBRARY_HANDBOOK_SECTIONS: tuple[SectionTemplate, ...] = (
    SectionTemplate(
        "overview",
        "Overview",
        "Go repository overview public purpose packages module responsibilities",
        purpose="Orient a Go library or CLI user to what the repository provides today.",
        must_cover=("library purpose", "main package/module", "public surface at a high level"),
        avoid=(
            "full API reference",
            "commit-derived architecture claims",
            "treating downstream usage examples as files or entrypoints in this repository",
        ),
        output_style="Keep it short enough to serve as a repository brief.",
        document_keys=("repository_brief",),
        retrieval_languages=("go",),
        retrieval_source_scopes=("runtime",),
        retrieval_include_tests=False,
    ),
    SectionTemplate(
        "public_api",
        "Public API",
        "exported Go API public types functions methods command package usage",
        purpose="Describe the exported Go API and how a consumer is expected to use it.",
        must_cover=("exported types/functions", "primary package responsibilities", "example usage patterns when evidenced"),
        avoid=(
            "private helper inventory",
            "APIs not present in evidence",
            "claiming that downstream application examples are repository implementation files",
        ),
        document_keys=("architecture_map", "api_reference"),
        retrieval_languages=("go",),
        retrieval_source_scopes=("runtime",),
        retrieval_include_tests=False,
    ),
    SectionTemplate(
        "command_lifecycle",
        "Command Lifecycle",
        "Go CLI command lifecycle execute run subcommands args validation cobra",
        purpose="Explain command execution flow for Go CLI-oriented libraries.",
        must_cover=("command construction", "execute/run lifecycle", "subcommands and validation hooks"),
        avoid=(
            "assuming Cobra unless evidence shows Cobra-specific names",
            "presenting consumer `main.go` or `cmd.Execute()` examples as entry points inside the library repository",
        ),
        document_keys=("architecture_map", "commands_reference"),
        retrieval_languages=("go",),
        retrieval_source_scopes=("runtime",),
        retrieval_include_tests=False,
    ),
    SectionTemplate(
        "flags_and_args",
        "Flags And Args",
        "Go CLI flags arguments validation pflag command options annotations cobra",
        purpose="Explain how flags and positional arguments are represented and validated.",
        must_cover=("flag definitions", "argument validation", "option/annotation mechanisms"),
        avoid=("listing every test-only flag as runtime API",),
        document_keys=("commands_reference", "configuration_reference"),
        retrieval_languages=("go",),
        retrieval_source_scopes=("runtime",),
        retrieval_include_tests=False,
    ),
    SectionTemplate(
        "completions",
        "Completions",
        "shell completion bash zsh fish powershell command completion generation cobra",
        purpose="Document shell completion support and extension points.",
        must_cover=("supported shells", "generation flow", "custom completion hooks when present"),
        avoid=("treating generated completion output as source design",),
        document_keys=("commands_reference",),
        retrieval_languages=("go",),
        retrieval_source_scopes=("runtime",),
        retrieval_include_tests=False,
    ),
    SectionTemplate(
        "doc_generation",
        "Documentation Generation",
        "Go CLI documentation generation markdown manpages command docs examples cobra",
        purpose="Explain repository-supported command documentation generation.",
        must_cover=("generated formats", "entry points for docs generation", "examples/tests that define behavior"),
        avoid=("marketing copy",),
        document_keys=("commands_reference",),
        retrieval_languages=("go",),
    ),
    SectionTemplate(
        "testing",
        "Testing",
        "Go tests test helpers command behavior completion tests",
        purpose="Explain how behavior is tested and where contributors should look first.",
        must_cover=("test focus areas", "test helpers", "commands to run tests"),
        avoid=("turning tests into runtime API claims"),
        document_keys=("onboarding_guide",),
        retrieval_languages=("go",),
        retrieval_source_scopes=("runtime", "test"),
        retrieval_include_tests=True,
    ),
    SectionTemplate(
        "package_map",
        "Package Map",
        "Go modules packages import graph responsibilities",
        purpose="Map Go packages/modules and their responsibilities.",
        must_cover=("module path", "important packages", "dependency relationships"),
        avoid=("unbounded import graph dumps",),
        document_keys=("architecture_map", "package_service_index"),
        retrieval_languages=("go",),
        retrieval_source_scopes=("runtime",),
        retrieval_include_tests=False,
    ),
    SectionTemplate(
        "build_run_test",
        "Build, Run, Test",
        "Go build test commands modules scripts local development",
        purpose="Tell a contributor how to build and test the Go project.",
        must_cover=("go test/build commands", "module/toolchain evidence", "local development notes"),
        avoid=("commands not supported by manifests or tests",),
        document_keys=("onboarding_guide", "commands_reference"),
    ),
    SectionTemplate(
        "known_gaps",
        "Known Gaps",
        "unsupported patterns generated files missing documentation known gaps",
        purpose="Record weak evidence, unsupported patterns and analysis limits.",
        must_cover=("missing evidence", "generated/truncated inputs", "areas needing manual verification"),
        avoid=("using commit history as current defects",),
        document_keys=("architecture_map",),
    ),
    SectionTemplate(
        "change_report",
        "Change Report",
        "recent commit history change events touched files packages merge commits",
        purpose="Summarize recent history separately from current Go API documentation.",
        must_cover=("recent change themes", "touched files/packages", "merge or noisy history"),
        avoid=("claiming current file absence from historical deletions alone",),
        output_style="Be cautious and distinguish history from current snapshot facts.",
        document_keys=("change_report",),
    ),
)

MONOREPO_WEB_APP_HANDBOOK_SECTIONS: tuple[SectionTemplate, ...] = (
    SectionTemplate(
        "overview",
        "Overview",
        "monorepo web application overview frontend backend services infrastructure",
        purpose="Orient a developer to the current monorepo product and its major parts.",
        must_cover=("frontend/backend split", "main services/apps", "current repository shape"),
        avoid=("deep per-service inventory", "commit-derived architecture claims"),
        output_style="Short brief with a small component summary.",
        document_keys=("repository_brief",),
    ),
    SectionTemplate(
        "service_map",
        "Service Map",
        "backend services frontend app gateway databases infrastructure workspace units",
        purpose="Map applications/services/workspace units to responsibilities.",
        must_cover=("frontend units", "backend services", "infrastructure units and databases"),
        avoid=("listing every file in each service",),
        document_keys=("architecture_map", "package_service_index"),
    ),
    SectionTemplate(
        "local_development",
        "Local Development",
        "local development docker compose package scripts go modules frontend backend",
        purpose="Tell a contributor how to run and inspect the monorepo locally.",
        must_cover=("frontend scripts", "backend modules/services", "compose or Docker evidence"),
        avoid=("inventing missing setup steps",),
        document_keys=("onboarding_guide", "commands_reference"),
    ),
    SectionTemplate(
        "request_flows",
        "Request Flows",
        "HTTP request flows gateway service interactions frontend backend clients",
        purpose="Describe end-to-end request flows visible from routes, clients and services.",
        must_cover=("gateway/front-to-back paths", "service interactions", "important handlers"),
        avoid=("claiming business behavior not supported by handlers/contracts"),
        document_keys=("architecture_map", "api_reference"),
    ),
    SectionTemplate(
        "data_model",
        "Data Model",
        "data models persistence DTO contracts database tables repository models",
        purpose="Explain the repository's data and contract model at a useful level.",
        must_cover=("domain models", "DTO/contracts", "persistence/database structures"),
        avoid=("raw SQL/JSON dumps",),
        document_keys=("architecture_map",),
    ),
    SectionTemplate(
        "api_surface",
        "API Surface",
        "HTTP routes OpenAPI Swagger API specs handlers request response contracts",
        purpose="Summarize externally visible HTTP/API surface.",
        must_cover=("routes/handlers", "OpenAPI/spec evidence", "request/response contracts when available"),
        avoid=("letting generated Swagger code dominate non-API sections"),
        document_keys=("api_reference",),
    ),
    SectionTemplate(
        "frontend",
        "Frontend",
        "frontend app routes components API clients package scripts assets",
        purpose="Describe frontend structure and how it talks to backend APIs.",
        must_cover=("routes/pages", "component areas", "API client/service directories"),
        avoid=("static asset inventory",),
        document_keys=("architecture_map", "package_service_index"),
    ),
    SectionTemplate(
        "configuration",
        "Configuration",
        "environment variables config files docker compose deployment settings",
        purpose="Explain configuration needed by the monorepo.",
        must_cover=("environment variables", "config files", "compose/deployment settings"),
        avoid=("secret values", "raw config dumps"),
        document_keys=("onboarding_guide", "configuration_reference"),
    ),
    SectionTemplate(
        "deployment",
        "Deployment",
        "deployment docker compose gitlab ci infrastructure database services",
        purpose="Summarize deployment and operational manifests visible in the repository.",
        must_cover=("Docker/compose/CI evidence", "service images", "database/infrastructure dependencies"),
        avoid=("assuming production topology beyond manifests",),
        document_keys=("architecture_map", "configuration_reference"),
    ),
    SectionTemplate(
        "known_gaps",
        "Known Gaps",
        "unsupported patterns generated files missing documentation known gaps",
        purpose="Record analysis limits and weak evidence for this monorepo.",
        must_cover=("generated/truncated inputs", "unsupported languages/patterns", "manual checks needed"),
        avoid=("treating historical commits as current bugs",),
        document_keys=("architecture_map",),
    ),
    SectionTemplate(
        "change_report",
        "Change Report",
        "recent commit history change events touched files packages merge commits",
        purpose="Summarize recent history separately from current monorepo architecture.",
        must_cover=("recent change themes", "touched files/packages", "merge-heavy or noisy history"),
        avoid=("claiming current file absence from historical deletions alone",),
        output_style="Separate historical observations from current snapshot facts.",
        document_keys=("change_report",),
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
