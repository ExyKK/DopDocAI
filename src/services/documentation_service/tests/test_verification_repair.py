import json

import pytest

from app.infra.llm_client import LlmCompletionResult, LlmProviderError, StubLlmCompletionProvider
from app.pipeline.generator import GeneratedDocument, GeneratedSection
from app.pipeline.llm_generation import LlmSectionGenerator
from app.pipeline.prompt_contract import PromptMessage, SectionPromptContract
from app.pipeline.repair import build_repair_attempts_manifest, build_repair_plan
from app.pipeline.verification import DocumentationVerifier


def test_deterministic_verification_finds_repairable_unknown_citation() -> None:
    section = _section("api_surface", "API Surface", "API uses `/v1/items` [S99].")
    contract = _contract("api_surface", "API Surface", source_ids=["S1"])

    report = DocumentationVerifier(
        StubLlmCompletionProvider(),
        mode="deterministic",
    ).verify(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="developer_handbook",
        requested_template_kind="developer_handbook",
        sections=[section],
        documents=[_document(section)],
        manifest=_manifest(section),
        contracts=[contract],
    )

    assert report.status == "failed"
    finding = next(item for item in report.findings if item.check_id == "citation_unknown_source")
    assert finding.repairable is True
    assert finding.section_key == "api_surface"

    plan = build_repair_plan(report)
    assert plan.has_repairs()
    assert plan.sections[0].section_key == "api_surface"


def test_llm_judge_findings_are_validated_and_recorded() -> None:
    provider = _JsonProvider(
        [
            {
                "status": "failed",
                "scores": {"groundedness": 0.2, "usefulness": 0.7},
                "findings": [
                    {
                        "severity": "error",
                        "category": "unsupported_claim",
                        "message": "Route claim is not supported by evidence.",
                        "claim": "The API exposes /v1/items.",
                        "section_key": "api_surface",
                        "source_ids": ["S1"],
                        "repairable": True,
                        "suggested_fix": "Remove the unsupported route claim.",
                    }
                ],
            },
            {
                "status": "passed",
                "scores": {"usefulness": 0.8},
                "findings": [],
            },
        ]
    )
    section = _section("api_surface", "API Surface", "API uses evidence [S1].")
    contract = _contract("api_surface", "API Surface", source_ids=["S1"])

    report = DocumentationVerifier(provider, mode="hybrid").verify(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="developer_handbook",
        requested_template_kind="developer_handbook",
        sections=[section],
        documents=[_document(section)],
        manifest=_manifest(section),
        contracts=[contract],
    )

    assert report.status == "failed"
    assert report.summary()["judge_calls_total"] == 2
    assert report.section_scores["api_surface"]["groundedness"] == 0.2
    assert any(item.origin == "llm_judge" for item in report.findings)


def test_invalid_judge_json_is_retryable_provider_error() -> None:
    provider = _TextProvider("not-json")
    section = _section(
        "overview",
        "Overview",
        "Репозиторий содержит достаточно подробное описание текущего состояния проекта [S1].",
    )
    contract = _contract("overview", "Overview", source_ids=["S1"])

    with pytest.raises(LlmProviderError) as exc:
        DocumentationVerifier(provider, mode="llm").verify(
            documentation_run_id="run-1",
            repository_id="repo-1",
            snapshot_id="snapshot-1",
            template_kind="developer_handbook",
            requested_template_kind="developer_handbook",
            sections=[section],
            documents=[_document(section)],
            manifest=_manifest(section),
            contracts=[contract],
        )

    assert exc.value.error_code == "verification_judge_invalid_response"
    assert exc.value.retryable is True
    assert exc.value.details["attempts_total"] == 3


def test_invalid_judge_json_retries_and_uses_json_mode() -> None:
    provider = _MixedProvider(
        [
            "not-json",
            {
                "status": "passed",
                "scores": {"groundedness": 0.9},
                "findings": [],
            },
            {
                "status": "passed",
                "scores": {"usefulness": 0.8},
                "findings": [],
            },
        ]
    )
    section = _section(
        "overview",
        "Overview",
        "Репозиторий содержит достаточно подробное описание текущего состояния проекта [S1].",
    )
    contract = _contract("overview", "Overview", source_ids=["S1"])

    report = DocumentationVerifier(provider, mode="llm", max_attempts=2).verify(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="developer_handbook",
        requested_template_kind="developer_handbook",
        sections=[section],
        documents=[_document(section)],
        manifest=_manifest(section),
        contracts=[contract],
    )

    assert report.status == "passed_with_warnings"
    assert provider.calls == 3
    assert provider.response_formats == [{"type": "json_object"}] * 3
    assert report.judge_calls[0].attempts_total == 2
    assert report.judge_calls[0].retry_errors[0]["error_code"] == "verification_judge_invalid_response"


def test_judge_failed_status_requires_findings() -> None:
    provider = _JsonProvider([{"status": "failed", "scores": {}, "findings": []}])
    section = _section("overview", "Overview", "Описание проекта [S1].")
    contract = _contract("overview", "Overview", source_ids=["S1"])

    with pytest.raises(LlmProviderError) as exc:
        DocumentationVerifier(provider, mode="llm", max_attempts=1).verify(
            documentation_run_id="run-1",
            repository_id="repo-1",
            snapshot_id="snapshot-1",
            template_kind="developer_handbook",
            requested_template_kind="developer_handbook",
            sections=[section],
            documents=[_document(section)],
            manifest=_manifest(section),
            contracts=[contract],
        )

    assert exc.value.error_code == "verification_judge_invalid_response"
    assert exc.value.retryable is True


def test_repair_section_returns_processed_section_body() -> None:
    provider = _TextProvider("Исправленная секция с корректной ссылкой [S1].")
    contract = _contract("overview", "Overview", source_ids=["S1"])

    repaired = LlmSectionGenerator(provider).repair_section(
        contract,
        current_markdown="## Overview\n\nBad claim [S99].",
        findings=[
            {
                "severity": "error",
                "category": "citation_integrity",
                "message": "Unknown citation.",
                "source_ids": ["S99"],
            }
        ],
        repair_round=1,
    ).section

    assert repaired.content_markdown.startswith("## Overview")
    assert "Исправленная секция" in repaired.content_markdown
    assert "### Sources" in repaired.content_markdown
    assert repaired.generation is not None
    assert repaired.generation["repair_round"] == 1


def test_repair_attempts_manifest_summarizes_unresolved_errors() -> None:
    bad_body = "This section contains a long enough unsupported technical claim [S99]."
    report = DocumentationVerifier(
        StubLlmCompletionProvider(),
        mode="deterministic",
    ).verify(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="developer_handbook",
        requested_template_kind="developer_handbook",
        sections=[_section("overview", "Overview", bad_body)],
        documents=[_document(_section("overview", "Overview", bad_body))],
        manifest=_manifest(_section("overview", "Overview", bad_body)),
        contracts=[_contract("overview", "Overview", source_ids=["S1"])],
    )

    plan = build_repair_plan(report)
    manifest = build_repair_attempts_manifest(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        attempts=[{"repair_round": 1, "section_key": "overview"}],
        plans=[plan],
        final_report=report,
    )

    assert manifest["summary"]["repair_rounds_total"] == 1
    assert manifest["summary"]["repaired_sections"] == ["overview"]
    assert manifest["summary"]["unresolved_errors_total"] == 1


def _section(key: str, title: str, body: str) -> GeneratedSection:
    return GeneratedSection(
        section_key=key,
        title=title,
        ordinal=1,
        content_markdown=f"## {title}\n\n{body}\n\n### Sources\n- [S1] source",
        source_count=1,
        generation={"quality_status": "ok"},
        section_spec={
            "key": key,
            "title": title,
            "purpose": "test",
            "must_cover": ["evidence-backed facts"],
            "avoid": ["unsupported claims"],
            "output_style": None,
            "document_keys": ["api_reference"],
        },
    )


def _document(section: GeneratedSection) -> GeneratedDocument:
    return GeneratedDocument(
        document_key="api_reference",
        title="API Reference",
        description="API facts.",
        file_name="api_reference.md",
        artifact_kind="document_api_reference",
        section_keys=(section.section_key,),
        content_markdown=f"# API Reference\n\n{section.content_markdown}",
    )


def _manifest(section: GeneratedSection) -> dict:
    return {
        "schema_version": 2,
        "documents": [
            {
                "document_key": "api_reference",
                "artifact": {"artifact_kind": "document_api_reference"},
            }
        ],
        "sections": [
            {
                "section_key": section.section_key,
                "artifact": {"artifact_kind": "section_markdown"},
            }
        ],
    }


def _contract(key: str, title: str, *, source_ids: list[str]) -> SectionPromptContract:
    return SectionPromptContract(
        schema_version=1,
        template_kind="developer_handbook",
        section_key=key,
        title=title,
        ordinal=1,
        section_spec={"key": key, "title": title, "must_cover": [], "avoid": []},
        output_language="ru",
        messages=[
            PromptMessage(role="system", content="system"),
            PromptMessage(role="developer", content="developer"),
            PromptMessage(
                role="user",
                content=json.dumps(
                    {
                        "evidence_pack": {
                            "sources": [
                                {
                                    "source_id": source_id,
                                    "content_markdown": f"Evidence for {source_id}",
                                }
                                for source_id in source_ids
                            ]
                        }
                    }
                ),
            ),
        ],
        source_ids=source_ids,
        source_index=[
            {
                "source_id": source_id,
                "title": f"Evidence {source_id}",
                "source_kind": "structured_artifact",
            }
            for source_id in source_ids
        ],
        estimated_input_tokens=100,
    )


class _JsonProvider:
    provider_name = "openrouter"

    def __init__(self, payloads: list[dict]):
        self._payloads = payloads

    def generate(self, messages, *, metadata=None, response_format=None):
        payload = self._payloads.pop(0)
        return _result(json.dumps(payload), provider=self.provider_name)


class _TextProvider:
    provider_name = "openrouter"

    def __init__(self, content: str):
        self._content = content

    def generate(self, messages, *, metadata=None, response_format=None):
        return _result(self._content, provider=self.provider_name)


class _MixedProvider:
    provider_name = "openrouter"

    def __init__(self, payloads: list[dict | str]):
        self._payloads = payloads
        self.calls = 0
        self.response_formats: list[dict | None] = []

    def generate(self, messages, *, metadata=None, response_format=None):
        self.calls += 1
        self.response_formats.append(response_format)
        payload = self._payloads.pop(0)
        content = json.dumps(payload) if isinstance(payload, dict) else payload
        return _result(content, provider=self.provider_name)


def _result(content: str, *, provider: str) -> LlmCompletionResult:
    return LlmCompletionResult(
        content=content,
        model="test-model",
        provider=provider,
        finish_reason="stop",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        latency_ms=1,
        response_id="response-1",
    )
