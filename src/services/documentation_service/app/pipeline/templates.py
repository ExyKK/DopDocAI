from dataclasses import dataclass


@dataclass(frozen=True)
class SectionTemplate:
    key: str
    title: str
    retrieval_query: str


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


def get_section_templates(template_kind: str) -> tuple[SectionTemplate, ...]:
    if template_kind == "developer_handbook":
        return DEVELOPER_HANDBOOK_SECTIONS

    raise ValueError(f"Unsupported documentation template: {template_kind}")
