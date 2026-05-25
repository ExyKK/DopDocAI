from app.pipeline.generator import DeveloperHandbookGenerator, GeneratedSection


def test_generator_builds_intent_based_documents_and_manifest_levels() -> None:
    generator = DeveloperHandbookGenerator()
    sections = [
        _section("overview", "Overview", 1, document_keys=["repository_brief"]),
        _section("service_map", "Service Map", 2, document_keys=["repository_brief", "architecture_map"]),
        _section("api_surface", "API Surface", 3, document_keys=["api_reference"]),
        _section("configuration", "Configuration", 4, document_keys=["onboarding_guide", "configuration_reference"]),
        _section("change_report", "Change Report", 5, document_keys=["change_report"]),
    ]

    documents = generator.assemble_documents(
        sections,
        template_kind="monorepo_web_app_handbook",
    )

    document_keys = {document.document_key for document in documents}
    assert {
        "repository_brief",
        "onboarding_guide",
        "architecture_map",
        "api_reference",
        "configuration_reference",
        "change_report",
    }.issubset(document_keys)
    assert all(document.file_name.endswith(".md") for document in documents)
    assert "# Repository Brief" in documents[0].content_markdown

    manifest = generator.build_manifest(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        attempt=2,
        publication_state="final",
        template_kind="monorepo_web_app_handbook",
        sections=sections,
        section_artifacts=[{"artifact_kind": "section_markdown"} for _ in sections],
        documents=documents,
        document_artifacts=[{"artifact_kind": document.artifact_kind} for document in documents],
        documentation_artifact={"artifact_kind": "documentation_markdown"},
    )

    assert manifest["schema_version"] == 2
    assert manifest["artifact_kind"] == "documentation_manifest"
    assert manifest["attempt"] == 2
    assert manifest["publication_state"] == "final"
    assert manifest["documents"][0]["section_keys"]
    assert manifest["sections"][0]["section_spec"]["document_keys"] == ["repository_brief"]


def test_index_document_points_to_generated_artifacts() -> None:
    generator = DeveloperHandbookGenerator()
    sections = [
        _section("overview", "Overview", 1, document_keys=["repository_brief"]),
        _section("change_report", "Change Report", 2, document_keys=["change_report"]),
    ]
    documents = generator.assemble_documents(sections, template_kind="developer_handbook")

    index = generator.assemble_index_document(
        documents,
        sections=sections,
        template_kind="developer_handbook",
    )

    assert index.startswith("# Developer Handbook")
    assert "(repository_brief.md)" in index
    assert "`change_report` - Change Report" in index


def _section(
    key: str,
    title: str,
    ordinal: int,
    *,
    document_keys: list[str],
) -> GeneratedSection:
    return GeneratedSection(
        section_key=key,
        title=title,
        ordinal=ordinal,
        content_markdown=f"## {title}\n\nGenerated content [S1].\n\n### Sources\n- [S1] source",
        source_count=1,
        generation={"quality_status": "ok"},
        section_spec={
            "key": key,
            "title": title,
            "purpose": "test",
            "must_cover": [],
            "avoid": [],
            "output_style": None,
            "document_keys": document_keys,
        },
    )
