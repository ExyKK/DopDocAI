import json

import pytest

from app.infra.llm_client import LlmCompletionResult, LlmProviderError, StubLlmCompletionProvider
from app.pipeline.generator import GeneratedDocument, GeneratedSection
from app.pipeline.llm_generation import LlmSectionGenerator, build_analysis_limitations_section
from app.pipeline.prompt_contract import PromptMessage, SectionPromptContract
from app.pipeline.repair import (
    RepairPlan,
    SectionRepairPlan,
    build_repair_attempts_manifest,
    build_repair_plan,
)
from app.pipeline.repair_evidence import build_repair_evidence_delta
from app.pipeline.verification import DocumentationVerifier, VerificationFinding


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


def test_llm_judge_self_contradictory_error_is_normalized() -> None:
    provider = _JsonProvider(
        [
            {
                "status": "failed",
                "scores": {"groundedness": 0.9},
                "findings": [
                    {
                        "severity": "error",
                        "category": "contradicted_claim",
                        "message": "No contradiction remains; this is actually supported.",
                        "claim": "The API uses evidence.",
                        "confidence": 0.9,
                        "repairable": True,
                        "repair_strategy": "remove_claim",
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

    assert all(item.severity != "error" for item in report.findings)
    assert report.summary()["judge_normalizations_total"] == 1
    finding = next(item for item in report.findings if item.origin == "llm_judge")
    assert finding.severity == "info"
    assert finding.repairable is False


def test_precise_missing_evidence_gap_can_stay_repairable_error() -> None:
    provider = _JsonProvider(
        [
            {
                "status": "failed",
                "scores": {"coverage": 0.4},
                "findings": [
                    {
                        "severity": "error",
                        "category": "not_enough_evidence",
                        "message": "Build commands need Makefile or CI evidence.",
                        "claim": "The project is built with make.",
                        "confidence": 0.82,
                        "repairable": True,
                        "repair_strategy": "expand_evidence",
                        "evidence_needed": "Makefile or GitHub Actions workflow for build commands",
                        "retrieval_hints": ["Makefile build", ".github/workflows"],
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
    section = _section("build_run_test", "Build Run Test", "Use make to build [S1].")
    contract = _contract(
        "build_run_test",
        "Build Run Test",
        source_ids=["S1"],
        template_kind="go_library_handbook",
    )

    report = DocumentationVerifier(provider, mode="hybrid").verify(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="go_library_handbook",
        requested_template_kind="developer_handbook",
        sections=[section],
        documents=[_document(section)],
        manifest=_manifest(section),
        contracts=[contract],
    )

    finding = next(item for item in report.findings if item.origin == "llm_judge")
    assert finding.severity == "error"
    assert finding.repair_strategy == "expand_evidence"

    plan = build_repair_plan(report)
    assert plan.sections[0].evidence_expansion_findings == [finding]


def test_post_repair_verification_carries_over_unchanged_section_judge_results() -> None:
    provider = _JsonProvider(
        [
            {
                "status": "passed_with_warnings",
                "scores": {"coverage": 0.7},
                "findings": [
                    {
                        "severity": "warning",
                        "category": "readability",
                        "message": "Minor readability issue.",
                    }
                ],
            },
            {"status": "passed", "scores": {"usefulness": 0.8}, "findings": []},
            {"status": "passed", "scores": {"groundedness": 0.95}, "findings": []},
            {"status": "passed", "scores": {"usefulness": 0.9}, "findings": []},
            {"status": "passed", "scores": {"usefulness": 0.9}, "findings": []},
        ]
    )
    unchanged = _section("overview", "Overview", "Overview content [S1].")
    repaired = _section("api_surface", "API Surface", "API uses evidence [S1].")
    unchanged_contract = _contract("overview", "Overview", source_ids=["S1"])
    repaired_contract = _contract("api_surface", "API Surface", source_ids=["S1"])
    verifier = DocumentationVerifier(provider, mode="llm")

    initial = verifier.verify(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="developer_handbook",
        requested_template_kind="developer_handbook",
        sections=[unchanged, repaired],
        documents=[_document(unchanged)],
        manifest=_manifest(unchanged),
        contracts=[unchanged_contract, repaired_contract],
    )
    followup = verifier.verify(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="developer_handbook",
        requested_template_kind="developer_handbook",
        sections=[unchanged, repaired],
        documents=[_document(repaired)],
        manifest=_manifest(repaired),
        contracts=[unchanged_contract, repaired_contract],
        repair_round=1,
        previous_report=initial,
        judge_section_keys={"api_surface"},
    )

    assert provider.generated_total == 5
    assert "overview" in followup.carried_over_judge_sections
    assert followup.section_scores["overview"]["coverage"] == 0.7
    assert any(item.section_key == "overview" for item in followup.findings)


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


def test_repair_evidence_delta_expands_contract_for_missing_coverage() -> None:
    finding = VerificationFinding(
        check_id="llm_judge_section_1",
        severity="error",
        category="missing_coverage",
        message="Command lifecycle is missing Execute evidence.",
        section_key="command_lifecycle",
        claim="Explain Command.Execute.",
        evidence_needed="runtime source for Command.Execute",
        repairable=True,
        repair_strategy="expand_evidence",
        retrieval_hints=["Command.Execute", "ExecuteC"],
        origin="llm_judge",
    )
    plan = RepairPlan(
        documentation_run_id="run-1",
        repair_round=1,
        sections=[SectionRepairPlan("command_lifecycle", [finding])],
    )
    contract = _contract(
        "command_lifecycle",
        "Command Lifecycle",
        source_ids=["S1"],
        template_kind="go_library_handbook",
    )
    retrieval = _RepairRetrieval()

    result = build_repair_evidence_delta(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="go_library_handbook",
        repair_plan=plan,
        contracts_by_section={contract.section_key: contract},
        retrieval=retrieval,
    )

    updated = result.updated_contracts["command_lifecycle"]
    assert "S2" in updated.source_ids
    assert result.prompt_deltas["command_lifecycle"]["sources"][0]["source_id"] == "S2"
    assert result.manifest["summary"]["sources_added_total"] >= 1
    assert result.manifest["sections"][0]["summary"]["budget"]["max_delta_sources_per_section"] == 3
    assert result.manifest["sections"][0]["findings"][0]["status"] == "sources_added"
    assert retrieval.calls[0]["filters"]["languages"] == ["go"]
    assert retrieval.calls[0]["filters"]["source_scopes"] == ["runtime"]
    assert retrieval.calls[0]["include_tests"] is False
    assert "Command.Execute" in updated.messages[-1].content


def test_repair_evidence_delta_skips_remove_claim_without_retrieval() -> None:
    finding = VerificationFinding(
        check_id="llm_judge_section_1",
        severity="error",
        category="unsupported_claim",
        message="Unsupported usage example.",
        section_key="public_api",
        claim="Consumer main.go is part of the repository.",
        repairable=True,
        repair_strategy="remove_claim",
        origin="llm_judge",
    )
    plan = RepairPlan(
        documentation_run_id="run-1",
        repair_round=1,
        sections=[SectionRepairPlan("public_api", [finding])],
    )
    contract = _contract("public_api", "Public API", source_ids=["S1"], template_kind="go_library_handbook")
    retrieval = _RepairRetrieval()

    result = build_repair_evidence_delta(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="go_library_handbook",
        repair_plan=plan,
        contracts_by_section={contract.section_key: contract},
        retrieval=retrieval,
    )

    assert retrieval.calls == []
    assert result.manifest["sections"][0]["findings"][0]["reason"] == "remove_claim_does_not_need_retrieval"


def test_repair_evidence_delta_build_run_test_does_not_inherit_go_runtime_filters() -> None:
    finding = VerificationFinding(
        check_id="llm_judge_section_1",
        severity="error",
        category="not_enough_evidence",
        message="Build commands need Makefile or CI evidence.",
        section_key="build_run_test",
        claim="Build uses make.",
        evidence_needed="Makefile or workflow build commands",
        retrieval_hints=["Makefile", ".github/workflows"],
        repairable=True,
        repair_strategy="expand_evidence",
        origin="llm_judge",
    )
    plan = RepairPlan(
        documentation_run_id="run-1",
        repair_round=1,
        sections=[SectionRepairPlan("build_run_test", [finding])],
    )
    contract = _contract(
        "build_run_test",
        "Build, Run, Test",
        source_ids=["S1"],
        template_kind="go_library_handbook",
    )
    retrieval = _RepairRetrieval()

    result = build_repair_evidence_delta(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="go_library_handbook",
        repair_plan=plan,
        contracts_by_section={contract.section_key: contract},
        retrieval=retrieval,
    )

    assert retrieval.calls[0]["filters"]["languages"] == []
    assert retrieval.calls[0]["filters"]["source_scopes"] == []
    assert all(
        source["source_kind"] != "go_symbol"
        for source in result.manifest["sections"][0]["added_sources"]
    )


def test_repair_evidence_delta_blocks_contradicted_claim_retrieval() -> None:
    finding = VerificationFinding(
        check_id="llm_judge_section_1",
        severity="error",
        category="contradicted_claim",
        message="Claim contradicts evidence.",
        section_key="overview",
        claim="Repository contains a main.go entrypoint.",
        repairable=True,
        repair_strategy="expand_evidence",
        origin="llm_judge",
    )
    plan = RepairPlan(
        documentation_run_id="run-1",
        repair_round=1,
        sections=[SectionRepairPlan("overview", [finding])],
    )
    contract = _contract("overview", "Overview", source_ids=["S1"], template_kind="go_library_handbook")
    retrieval = _RepairRetrieval()

    result = build_repair_evidence_delta(
        documentation_run_id="run-1",
        repository_id="repo-1",
        snapshot_id="snapshot-1",
        template_kind="go_library_handbook",
        repair_plan=plan,
        contracts_by_section={contract.section_key: contract},
        retrieval=retrieval,
    )

    assert retrieval.calls == []
    assert result.updated_contracts == {}
    assert result.manifest["sections"][0]["findings"][0]["retrieval_policy"] == "blocked"
    assert result.manifest["sections"][0]["findings"][0]["added_source_ids"] == []


def test_analysis_limitations_section_is_deterministic_and_scopes_absence_to_evidence() -> None:
    contract = _contract("analysis_limitations", "Analysis Limitations", source_ids=["S1"])

    generated = build_analysis_limitations_section(contract).section

    assert generated.generation is not None
    assert generated.generation["provider"] == "deterministic"
    assert "не означает их отсутствие в репозитории" in generated.content_markdown
    assert "### Sources" in generated.content_markdown


def test_analysis_limitations_repository_absence_claim_is_hard_error() -> None:
    section = _section(
        "analysis_limitations",
        "Analysis Limitations",
        "Файл `cmd/root.go` отсутствует в репозитории [S1].",
    )
    contract = _contract("analysis_limitations", "Analysis Limitations", source_ids=["S1"])

    report = DocumentationVerifier(StubLlmCompletionProvider(), mode="deterministic").verify(
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
    assert any(
        item.check_id == "analysis_limitations_repository_absence_claim"
        for item in report.findings
    )


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


def _contract(
    key: str,
    title: str,
    *,
    source_ids: list[str],
    template_kind: str = "developer_handbook",
) -> SectionPromptContract:
    return SectionPromptContract(
        schema_version=1,
        template_kind=template_kind,
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
                "language": "go" if template_kind == "go_library_handbook" else None,
                "source_scope": "runtime" if template_kind == "go_library_handbook" else None,
            }
            for source_id in source_ids
        ],
        estimated_input_tokens=100,
    )


class _RepairRetrieval:
    def __init__(self) -> None:
        self.calls = []

    def search(self, snapshot_id: str, query: str, *, top_k=None, filters=None, include_tests=None):
        self.calls.append(
            {
                "snapshot_id": snapshot_id,
                "query": query,
                "top_k": top_k,
                "filters": filters or {},
                "include_tests": include_tests,
            }
        )
        return [
            _retrieved(
                "docs-1",
                "site/content/user_guide.md",
                "markdown",
                "docs",
                "Consumer main.go calls cmd.Execute().",
            ),
            _retrieved(
                "runtime-1",
                "command.go",
                "go",
                "runtime",
                "func (c *Command) Execute() error { return c.ExecuteC() }",
                symbol_name="cobra.Command.Execute",
            ),
        ]


def _retrieved(
    chunk_id: str,
    file_path: str,
    language: str,
    source_scope: str,
    text: str,
    *,
    symbol_name: str | None = None,
):
    from app.infra.retrieval_client import RetrievedSource

    return RetrievedSource(
        chunk_id=chunk_id,
        score=0.9,
        text=text,
        file_path=file_path,
        language=language,
        source_scope=source_scope,
        start_line=1,
        end_line=5,
        symbol_name=symbol_name,
        source_kind="go_symbol" if language == "go" else "file_slice",
    )


class _JsonProvider:
    provider_name = "openrouter"

    def __init__(self, payloads: list[dict]):
        self._payloads = payloads
        self.generated_total = 0

    def generate(self, messages, *, metadata=None, response_format=None):
        self.generated_total += 1
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
