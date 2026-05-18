import json
from pathlib import Path

from app.pipeline.evidence import SectionEvidence
from app.pipeline.evidence_pack import EvidencePackBudget, build_evidence_pack
from app.pipeline.prompt_contract import build_section_prompt_contract


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

    contract = build_section_prompt_contract(section, output_language="ru")
    payload = contract.to_dict()

    assert payload["schema_version"] == 1
    assert payload["source_ids"] == ["S1"]
    assert "Use only source ids listed in the evidence pack" in payload["messages"][1]["content"]
    assert '"allowed_source_ids": [' in payload["messages"][2]["content"]


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

    contract = build_section_prompt_contract(section, output_language=fixture["output_language"])
    developer_message = contract.messages[1].content

    assert [message.role for message in contract.messages] == fixture["expected_message_roles"]
    for rule in fixture["required_rules"]:
        assert rule in developer_message
