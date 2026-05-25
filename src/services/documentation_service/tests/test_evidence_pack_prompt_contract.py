import json
from pathlib import Path

from app.infra.retrieval_client import RetrievedSource
from app.pipeline.evidence import EvidencePlanner, SectionEvidence
from app.pipeline.evidence_pack import EvidencePackBudget, build_evidence_pack
from app.pipeline.prompt_contract import build_section_prompt_contract
from app.pipeline.rendered_evidence import build_rendered_evidence_pack
from app.pipeline.templates import SectionTemplate


def test_evidence_pack_respects_budget_and_records_diagnostics() -> None:
    section = SectionEvidence(
        section_key="overview",
        title="Overview",
        ordinal=1,
        status="evidence_ready",
        sources=[
            {
                "ordinal": 1,
                "snapshot_id": "snapshot-1",
                "source_kind": "analysis_artifact",
                "note": "project_model: workspace_units",
            },
            {
                "ordinal": 2,
                "snapshot_id": "snapshot-1",
                "source_kind": "go_symbol",
                "file_path": "cmd/server/main.go",
                "chunk_id": "chunk-1",
                "note": "retrieval: startup",
            },
        ],
        evidence={
            "workspace_units": [
                {"id": f"unit-{index}", "root_path": f"service-{index}"}
                for index in range(6)
            ],
            "retrieval_query": "startup",
            "retrieval_matches": [
                {
                    "chunk_id": "chunk-1",
                    "file_path": "cmd/server/main.go",
                    "symbol_name": "main",
                    "source_kind": "go_symbol",
                    "score": 0.91,
                    "text": "func main() {\n" + ("println(\"boot\")\n" * 200) + "}",
                }
            ],
        },
    )

    pack = build_evidence_pack(
        section_key=section.section_key,
        title=section.title,
        ordinal=section.ordinal,
        evidence=section.evidence,
        sources=section.sources,
        budget=EvidencePackBudget(max_tokens=500, max_source_tokens=100, max_sources=2),
    )

    assert pack.estimated_tokens <= 500
    assert len(pack.sources) <= 2
    assert pack.truncated_sources
    assert pack.sources[0].source_id == "S1"
    assert pack.sources[0].selection_reason.startswith("structured")


def test_prompt_contract_uses_only_evidence_pack_source_ids() -> None:
    section = SectionEvidence(
        section_key="entry_points",
        title="Entry Points",
        ordinal=4,
        status="evidence_ready",
        sources=[],
        section_spec={
            "key": "entry_points",
            "title": "Entry Points",
            "purpose": "Describe startup and externally reachable handlers.",
            "must_cover": ["startup paths", "handlers"],
            "avoid": ["inventing missing APIs"],
            "output_style": "compact",
            "document_keys": ["architecture_map", "api_reference"],
        },
        evidence={"entry_points": [{"file_path": "cmd/server/main.go"}]},
    )
    section.evidence_pack = build_evidence_pack(
        section_key=section.section_key,
        title=section.title,
        ordinal=section.ordinal,
        evidence=section.evidence,
        sources=section.sources,
        budget=EvidencePackBudget(max_tokens=10_000, max_source_tokens=2_000, max_sources=10),
    )
    section.rendered_evidence_pack = build_rendered_evidence_pack(section.evidence_pack)

    contract = build_section_prompt_contract(
        section,
        template_kind="developer_handbook",
        output_language="ru",
    )
    payload = contract.to_dict()

    assert payload["schema_version"] == 1
    assert payload["template_kind"] == "developer_handbook"
    assert payload["section_spec"]["purpose"] == "Describe startup and externally reachable handlers."
    assert payload["source_ids"] == ["S1"]
    assert payload["source_index"][0]["source_id"] == "S1"
    assert "Use only source ids listed in the evidence pack" in payload["messages"][1]["content"]
    assert "Follow the `section_spec` purpose" in payload["messages"][1]["content"]
    assert "return the section body only" in payload["messages"][1]["content"]
    assert '"allowed_source_ids": [' in payload["messages"][2]["content"]
    assert '"section_spec": {' in payload["messages"][2]["content"]
    assert '"must_cover": [' in payload["messages"][2]["content"]
    assert '"format": "rendered_markdown_sources"' in payload["messages"][2]["content"]
    assert '"content_markdown":' in payload["messages"][2]["content"]


def test_rendered_evidence_table_handles_numeric_workspace_counts() -> None:
    section = SectionEvidence(
        section_key="repository_structure",
        title="Repository Structure",
        ordinal=2,
        status="evidence_ready",
        sources=[],
        evidence={
            "workspace_units": [
                {
                    "workspace_unit_id": "backend:api",
                    "unit_kind": "go_service",
                    "root_path": "backend/api",
                    "roles": ["backend"],
                    "frameworks": ["gin"],
                    "file_counts": {"files_total": 42},
                    "key_files": [{"path": "backend/api/go.mod"}],
                }
            ]
        },
    )
    section.evidence_pack = build_evidence_pack(
        section_key=section.section_key,
        title=section.title,
        ordinal=section.ordinal,
        evidence=section.evidence,
        sources=section.sources,
        budget=EvidencePackBudget(max_tokens=10_000, max_source_tokens=2_000, max_sources=10),
    )

    rendered = build_rendered_evidence_pack(section.evidence_pack)
    markdown = rendered.sources[0].content_markdown

    assert "| backend:api | go_service | backend/api | backend | gin | 42 | backend/api/go.mod |" in markdown


def test_prompt_contract_fixture_rules_are_present() -> None:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "prompt_contract"
        / "developer_handbook_entry_points.schema-v1.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    section = SectionEvidence(
        section_key=fixture["section_key"],
        title=fixture["title"],
        ordinal=4,
        status="evidence_ready",
        sources=[],
        evidence={"entry_points": [{"file_path": "cmd/server/main.go"}]},
    )
    section.evidence_pack = build_evidence_pack(
        section_key=section.section_key,
        title=section.title,
        ordinal=section.ordinal,
        evidence=section.evidence,
        sources=section.sources,
        budget=EvidencePackBudget(),
    )
    section.rendered_evidence_pack = build_rendered_evidence_pack(section.evidence_pack)

    contract = build_section_prompt_contract(
        section,
        template_kind=fixture["template_kind"],
        output_language=fixture["output_language"],
    )
    developer_message = contract.messages[1].content

    assert [message.role for message in contract.messages] == fixture["expected_message_roles"]
    for rule in fixture["required_rules"]:
        assert rule in developer_message


def test_evidence_planner_filters_generated_retrieval_for_generic_sections() -> None:
    templates = (
        SectionTemplate(
            key="known_gaps",
            title="Known Gaps",
            retrieval_query="generated files gaps",
        ),
    )
    planner = EvidencePlanner(_FakeRetrievalClient())

    sections = planner.plan(snapshot_id="snapshot-1", templates=templates, artifacts={})

    section = sections[0]
    matches = section.evidence["retrieval_matches"]
    assert [match["file_path"] for match in matches] == ["cmd/server/main.go"]
    assert all(match["source_scope"] != "generated" for match in matches)
    assert section.rendered_evidence_pack is not None
    rendered = section.rendered_evidence_pack.to_dict()
    assert "backend/service/docs/docs.go" not in json.dumps(rendered, ensure_ascii=False)


def test_go_library_runtime_sections_filter_consumer_docs_from_retrieval() -> None:
    templates = (
        SectionTemplate(
            key="command_lifecycle",
            title="Command Lifecycle",
            retrieval_query="cobra command Execute lifecycle",
            retrieval_languages=("go",),
            retrieval_source_scopes=("runtime",),
            retrieval_include_tests=False,
        ),
    )
    retrieval = _GoLibraryRetrievalClient()
    planner = EvidencePlanner(retrieval)

    sections = planner.plan(snapshot_id="snapshot-1", templates=templates, artifacts={})

    assert retrieval.calls[0]["filters"]["languages"] == ["go"]
    assert retrieval.calls[0]["filters"]["source_scopes"] == ["runtime"]
    assert retrieval.calls[0]["include_tests"] is False
    matches = sections[0].evidence["retrieval_matches"]
    assert [match["file_path"] for match in matches] == ["command.go"]


def test_commit_evidence_keeps_sha_subject_status_boundaries() -> None:
    planner = EvidencePlanner(None)
    templates = (
        SectionTemplate(
            key="change_report",
            title="Change Report",
            retrieval_query="recent commits",
        ),
    )
    artifacts = {
        "project_model": {
            "files": [
                {"path": "docker-compose.yml"},
            ],
        },
        "package_graph": {},
        "config_inventory": {},
        "commit_log": {
            "summary": {"commits_total": 2},
            "commits": [
                {
                    "sha": "cbba05f4ba17d73a5508a8b746f06e15bfd69b87",
                    "short_sha": "cbba05f4ba17",
                    "subject": "Added media support finallygit add .git add .",
                    "parents": ["p1"],
                    "is_merge": False,
                    "touched_files": [
                        {
                            "path": "docker-compose.yml",
                            "status": "D",
                            "change_type": "deleted",
                        }
                    ],
                },
                {
                    "sha": "733280edb3887e1b1c6931cbb860bc28b47e7308",
                    "short_sha": "733280edb388",
                    "subject": "fucking docker compose",
                    "parents": ["p2"],
                    "is_merge": False,
                    "touched_files": [
                        {
                            "path": "docker-compose.yml",
                            "status": "A",
                            "change_type": "added",
                        }
                    ],
                },
            ],
            "touched_files": [
                {
                    "path": "docker-compose.yml",
                    "commits_total": 2,
                    "latest_commit_sha": "cbba05f4ba17d73a5508a8b746f06e15bfd69b87",
                    "change_type_counts": {"added": 1, "deleted": 1},
                }
            ],
        },
    }

    sections = planner.plan(snapshot_id="snapshot-1", templates=templates, artifacts=artifacts)

    events = sections[0].evidence["change_events"]
    deleted_event = events[0]
    added_event = events[1]
    assert deleted_event["short_sha"] == "cbba05f4ba17"
    assert deleted_event["subject"] == "Added media support finallygit add .git add ."
    assert deleted_event["change_type"] == "deleted"
    assert deleted_event["current_file_state"] == "present"
    assert added_event["short_sha"] == "733280edb388"
    assert added_event["subject"] == "fucking docker compose"

    assert sections[0].rendered_evidence_pack is not None
    rendered = sections[0].rendered_evidence_pack.to_dict()
    rendered_text = json.dumps(rendered, ensure_ascii=False)
    assert "cbba05f4ba17" in rendered_text
    assert "fucking docker compose" in rendered_text
    assert "Do not infer current file absence" in rendered_text


def test_overview_does_not_receive_commit_history_evidence() -> None:
    planner = EvidencePlanner(None)
    templates = (
        SectionTemplate(
            key="overview",
            title="Overview",
            retrieval_query="overview",
        ),
    )
    artifacts = {
        "project_model": {"summary": {"files_total": 1}},
        "package_graph": {},
        "config_inventory": {},
        "commit_log": {
            "summary": {"commits_total": 1},
            "commits": [
                {
                    "sha": "abc",
                    "short_sha": "abc",
                    "subject": "historical change",
                    "touched_files": [{"path": "old.go", "change_type": "deleted"}],
                }
            ],
        },
    }

    sections = planner.plan(snapshot_id="snapshot-1", templates=templates, artifacts=artifacts)

    assert "change_events" not in sections[0].evidence
    assert "commit_summary" not in sections[0].evidence


class _FakeRetrievalClient:
    def search(self, snapshot_id: str, query: str, **kwargs) -> list[RetrievedSource]:
        return [
            RetrievedSource(
                chunk_id="generated-1",
                score=0.9,
                text="generated swagger",
                file_path="backend/service/docs/docs.go",
                language="go",
                source_scope="generated",
                start_line=1,
                end_line=80,
                symbol_name="docs.go",
                source_kind="generated",
            ),
            RetrievedSource(
                chunk_id="runtime-1",
                score=0.7,
                text="func main() {}",
                file_path="cmd/server/main.go",
                language="go",
                source_scope="runtime",
                start_line=1,
                end_line=3,
                symbol_name="main",
                source_kind="go_symbol",
            ),
        ]


class _GoLibraryRetrievalClient:
    def __init__(self) -> None:
        self.calls = []

    def search(self, snapshot_id: str, query: str, **kwargs) -> list[RetrievedSource]:
        self.calls.append(kwargs)
        return [
            RetrievedSource(
                chunk_id="docs-1",
                score=0.95,
                text="Consumer app creates a main.go and calls cmd.Execute().",
                file_path="site/content/user_guide.md",
                language="markdown",
                source_scope="docs",
                start_line=10,
                end_line=20,
                symbol_name="user_guide.md",
                source_kind="file_slice",
            ),
            RetrievedSource(
                chunk_id="runtime-1",
                score=0.91,
                text="func (c *Command) Execute() error { return c.ExecuteC() }",
                file_path="command.go",
                language="go",
                source_scope="runtime",
                start_line=1080,
                end_line=1100,
                symbol_name="cobra.Command.Execute",
                source_kind="go_symbol",
            ),
        ]
