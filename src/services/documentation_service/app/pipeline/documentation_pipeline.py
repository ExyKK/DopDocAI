import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any

from app.infra.llm_client import LlmCompletionProvider
from app.infra.object_storage import ObjectStorageClient
from app.infra.repository_service_client import AnalysisArtifactRef, RepositoryServiceClient
from app.infra.retrieval_client import RetrievalClient
from app.pipeline.classification import classify_repository
from app.pipeline.evidence import EvidencePlanner, SectionEvidence
from app.pipeline.evidence_pack import (
    EvidencePack,
    EvidencePackBudget,
    build_evidence_pack_manifest,
)
from app.pipeline.generator import DeveloperHandbookGenerator, GeneratedDocument, GeneratedSection
from app.pipeline.llm_generation import LlmSectionGenerator
from app.pipeline.pipeline_trace import PipelineTrace, error_payload
from app.pipeline.prompt_contract import (
    SectionPromptContract,
    build_prompt_contract_manifest,
    build_section_prompt_contract,
)
from app.pipeline.rendered_evidence import (
    RenderedEvidencePack,
    build_rendered_evidence_pack_manifest,
)
from app.pipeline.repair import RepairPlan, build_repair_attempts_manifest, build_repair_plan
from app.pipeline.repair_evidence import build_repair_evidence_delta
from app.pipeline.templates import get_section_templates, select_documentation_template
from app.pipeline.verification import (
    DocumentationVerificationError,
    DocumentationVerifier,
    VerificationMode,
    VerificationReport,
)
from app.worker.job_store import ClaimedDocumentationRun

REQUIRED_ANALYSIS_ARTIFACTS = (
    "project_model",
    "package_graph",
    "config_inventory",
    "commit_log",
)

logger = logging.getLogger("documentation_pipeline")


@dataclass(frozen=True)
class DocumentationPlanResult:
    sections: list[SectionEvidence]
    summary: dict[str, Any]


@dataclass(frozen=True)
class _PublishedDocumentBundle:
    documents: list[GeneratedDocument]
    document_artifacts: list[dict[str, Any]]
    documentation_artifact: dict[str, Any]


class DocumentationGenerationPipeline:
    def __init__(
        self,
        *,
        repository_service: RepositoryServiceClient,
        storage: ObjectStorageClient,
        retrieval: RetrievalClient | None,
        llm_provider: LlmCompletionProvider,
        evidence_pack_budget: EvidencePackBudget | None = None,
        prompt_output_language: str = "ru",
        verification_mode: VerificationMode = "hybrid",
        max_repair_rounds: int = 2,
        llm_call_max_attempts: int = 3,
        llm_call_retry_delay_s: float = 1.0,
        llm_json_mode_enabled: bool = True,
        pipeline_trace_enabled: bool = True,
    ):
        self._repository_service = repository_service
        self._storage = storage
        self._retrieval = retrieval
        self._planner = EvidencePlanner(retrieval, budget=evidence_pack_budget)
        self._generator = DeveloperHandbookGenerator()
        self._section_generator = LlmSectionGenerator(
            llm_provider,
            max_attempts=llm_call_max_attempts,
            retry_delay_s=llm_call_retry_delay_s,
        )
        self._verifier = DocumentationVerifier(
            llm_provider,
            mode=verification_mode,
            max_attempts=llm_call_max_attempts,
            retry_delay_s=llm_call_retry_delay_s,
            json_mode_enabled=llm_json_mode_enabled,
        )
        self._prompt_output_language = prompt_output_language
        self._max_repair_rounds = max(0, max_repair_rounds)
        self._pipeline_trace_enabled = pipeline_trace_enabled
        self._trace: PipelineTrace | None = None
        self._published_artifacts: list[dict[str, Any]] = []
        self._failure_context: dict[str, Any] = {}
        self._pipeline_trace_published = False

    def build_developer_handbook(
        self,
        run: ClaimedDocumentationRun,
        *,
        report_progress,
    ) -> DocumentationPlanResult:
        self._trace = self._new_trace(run)
        self._published_artifacts = []
        self._failure_context = {}
        self._pipeline_trace_published = False
        self._record_trace(
            "pipeline_started",
            documentation_run_id=run.id,
            repository_id=run.repository_id,
            snapshot_id=run.snapshot_id,
            requested_template_kind=run.template_kind,
            attempt=run.attempt,
        )
        self._record_attempt_state(run)
        try:
            return self._build_developer_handbook(run, report_progress=report_progress)
        except Exception as exc:
            context = self._failure_context or {}
            self._publish_pipeline_error_safely(
                run=run,
                stage=str(context.get("stage") or "pipeline"),
                error=exc,
                section_key=context.get("section_key"),
                repair_round=context.get("repair_round"),
                completed_sections=context.get("completed_sections"),
            )
            raise
        finally:
            self._trace = None
            self._published_artifacts = []
            self._failure_context = {}
            self._pipeline_trace_published = False

    def _build_developer_handbook(
        self,
        run: ClaimedDocumentationRun,
        *,
        report_progress,
    ) -> DocumentationPlanResult:
        report_progress("loading_project_model", 20)
        self._record_trace("stage_started", stage="loading_project_model", progress_pct=20)
        refs = self._repository_service.list_analysis_artifacts(run.repository_id, run.snapshot_id)
        latest_refs = _latest_by_kind(refs)
        artifacts = self._load_required_artifacts(latest_refs)
        repository_classification = classify_repository(artifacts)
        template_selection = select_documentation_template(run.template_kind, repository_classification)
        effective_template_kind = template_selection.effective_template_kind
        templates = get_section_templates(effective_template_kind)
        self._record_template_selection(
            requested_template_kind=run.template_kind,
            effective_template_kind=effective_template_kind,
            template_selection=template_selection.to_dict(),
            repository_classification=repository_classification.to_dict(),
        )

        report_progress("planning_sections", 35, progress_total=len(templates))
        self._record_trace(
            "stage_started",
            stage="planning_sections",
            progress_pct=35,
            sections_total=len(templates),
        )
        sections = self._planner.plan(
            snapshot_id=run.snapshot_id,
            templates=templates,
            artifacts=artifacts,
        )
        prompt_contracts = _attach_prompt_contracts(
            sections,
            template_kind=effective_template_kind,
            output_language=self._prompt_output_language,
        )
        evidence_packs = _evidence_packs(sections)
        rendered_evidence_packs = _rendered_evidence_packs(sections)

        report_progress("retrieving_evidence", 65, progress_current=len(sections), progress_total=len(sections))
        self._record_trace(
            "stage_completed",
            stage="planning_sections",
            progress_pct=65,
            sections_total=len(sections),
            evidence_sources_total=sum(len(section.sources) for section in sections),
        )
        self._repository_service.replace_documentation_sections(
            run.id,
            [section.to_request() for section in sections],
        )

        evidence_pack_artifact = self._publish_json(
            run=run,
            artifact_kind="evidence_pack_manifest",
            section_key=None,
            key=f"{_attempt_prefix(run)}/evidence_packs.schema-v1.json",
            payload=build_evidence_pack_manifest(
                documentation_run_id=run.id,
                repository_id=run.repository_id,
                snapshot_id=run.snapshot_id,
                template_kind=effective_template_kind,
                packs=evidence_packs,
            ),
        )
        prompt_contract_artifact = self._publish_json(
            run=run,
            artifact_kind="prompt_contract_manifest",
            section_key=None,
            key=f"{_attempt_prefix(run)}/prompt_contracts.schema-v1.json",
            payload=build_prompt_contract_manifest(
                documentation_run_id=run.id,
                repository_id=run.repository_id,
                snapshot_id=run.snapshot_id,
                template_kind=effective_template_kind,
                contracts=prompt_contracts,
            ),
        )
        rendered_evidence_pack_artifact = self._publish_json(
            run=run,
            artifact_kind="rendered_evidence_pack_manifest",
            section_key=None,
            key=f"{_attempt_prefix(run)}/rendered_evidence_packs.schema-v1.json",
            payload=build_rendered_evidence_pack_manifest(
                documentation_run_id=run.id,
                repository_id=run.repository_id,
                snapshot_id=run.snapshot_id,
                template_kind=effective_template_kind,
                packs=rendered_evidence_packs,
            ),
        )

        report_progress("generating_sections", 78, progress_current=0, progress_total=len(sections))
        generated_sections: list[GeneratedSection] = []
        section_artifacts_by_key: dict[str, dict[str, Any]] = {}
        for index, contract in enumerate(prompt_contracts, start=1):
            self._record_trace(
                "llm_section_generation_started",
                stage="generating_sections",
                llm_task="documentation_section_generation",
                section_key=contract.section_key,
                source_count=len(contract.source_ids),
                estimated_input_tokens=contract.estimated_input_tokens,
            )
            try:
                generated = self._section_generator.generate_section(contract)
            except Exception as exc:
                self._set_failure_context(
                    stage="generating_sections",
                    section_key=contract.section_key,
                    completed_sections=[
                        {
                            "section_key": section.section_key,
                            "title": section.title,
                            "ordinal": section.ordinal,
                        }
                        for section in generated_sections
                    ],
                )
                self._publish_generation_error_safely(
                    run=run,
                    contract=contract,
                    template_kind=effective_template_kind,
                    error=exc,
                    completed_sections=generated_sections,
                )
                raise

            section = generated.section
            generated_sections.append(section)
            self._record_llm_generation_completed(
                "llm_section_generation_completed",
                section=section,
                llm_task="documentation_section_generation",
            )
            section_artifacts_by_key[section.section_key] = self._publish_section_markdown(run, section)
            report_progress("generating_sections", 78, progress_current=index, progress_total=len(sections))

        bundle = self._publish_document_bundle(
            run=run,
            generated_sections=generated_sections,
            template_kind=effective_template_kind,
            publication_state="draft",
        )

        verification_reports: list[VerificationReport] = []
        repair_plans: list[RepairPlan] = []
        repair_attempts: list[dict[str, Any]] = []
        repair_evidence_delta_artifacts: list[dict[str, Any]] = []
        contract_by_section = {contract.section_key: contract for contract in prompt_contracts}

        for repair_round in range(self._max_repair_rounds + 1):
            report_progress(
                "verifying_documentation",
                86,
                progress_current=repair_round,
                progress_total=self._max_repair_rounds + 1,
            )
            current_manifest = self._build_manifest(
                run=run,
                template_kind=effective_template_kind,
                template_selection=template_selection.to_dict(),
                repository_classification=repository_classification.to_dict(),
                generated_sections=generated_sections,
                section_artifacts_by_key=section_artifacts_by_key,
                bundle=bundle,
                evidence_pack_artifact=evidence_pack_artifact,
                prompt_contract_artifact=prompt_contract_artifact,
                rendered_evidence_pack_artifact=rendered_evidence_pack_artifact,
            )
            try:
                report = self._verifier.verify(
                    documentation_run_id=run.id,
                    repository_id=run.repository_id,
                    snapshot_id=run.snapshot_id,
                    template_kind=effective_template_kind,
                    requested_template_kind=run.template_kind,
                    sections=generated_sections,
                    documents=bundle.documents,
                    manifest=current_manifest,
                    contracts=prompt_contracts,
                    repair_round=repair_round,
                )
            except Exception:
                self._set_failure_context(
                    stage="verifying_documentation",
                    repair_round=repair_round,
                    completed_sections=[
                        {
                            "section_key": section.section_key,
                            "title": section.title,
                            "ordinal": section.ordinal,
                        }
                        for section in generated_sections
                    ],
                )
                raise
            verification_reports.append(report)
            self._record_verification_completed(report)
            if not report.has_hard_errors():
                break
            if repair_round >= self._max_repair_rounds:
                break

            plan = build_repair_plan(report)
            repair_plans.append(plan)
            if not plan.has_repairs() or plan.unresolved_findings:
                break

            repair_evidence_delta = build_repair_evidence_delta(
                documentation_run_id=run.id,
                repository_id=run.repository_id,
                snapshot_id=run.snapshot_id,
                template_kind=effective_template_kind,
                repair_plan=plan,
                contracts_by_section=contract_by_section,
                retrieval=self._retrieval,
            )
            delta_artifact = self._publish_json(
                run=run,
                artifact_kind="repair_evidence_delta",
                section_key=None,
                key=(
                    f"{_attempt_prefix(run)}/repair_evidence_delta."
                    f"round-{plan.repair_round}.schema-v1.json"
                ),
                payload=repair_evidence_delta.manifest,
            )
            repair_evidence_delta_artifacts.append(delta_artifact)
            if repair_evidence_delta.updated_contracts:
                contract_by_section.update(repair_evidence_delta.updated_contracts)
                prompt_contracts = _replace_prompt_contracts(
                    prompt_contracts,
                    repair_evidence_delta.updated_contracts,
                )
            self._record_trace(
                "repair_evidence_delta_built",
                stage="repairing_documentation",
                repair_round=plan.repair_round,
                sections_total=repair_evidence_delta.manifest["summary"]["sections_total"],
                sources_added_total=repair_evidence_delta.manifest["summary"]["sources_added_total"],
                queries_total=repair_evidence_delta.manifest["summary"]["queries_total"],
            )

            report_progress(
                "repairing_documentation",
                88,
                progress_current=repair_round + 1,
                progress_total=self._max_repair_rounds,
            )
            for section_plan in plan.sections:
                contract = contract_by_section.get(section_plan.section_key)
                current_section = _section_by_key(generated_sections, section_plan.section_key)
                if contract is None or current_section is None:
                    continue

                self._record_trace(
                    "llm_section_repair_started",
                    stage="repairing_documentation",
                    llm_task="documentation_section_repair",
                    section_key=contract.section_key,
                    repair_round=plan.repair_round,
                    findings_total=len(section_plan.findings),
                )
                try:
                    repaired = self._section_generator.repair_section(
                        contract,
                        current_markdown=current_section.content_markdown,
                        findings=[finding.to_dict() for finding in section_plan.findings],
                        repair_round=plan.repair_round,
                        repair_evidence_delta=repair_evidence_delta.prompt_deltas.get(
                            section_plan.section_key
                        ),
                    ).section
                except Exception:
                    self._set_failure_context(
                        stage="repairing_documentation",
                        section_key=contract.section_key,
                        repair_round=plan.repair_round,
                        completed_sections=[
                            {
                                "section_key": section.section_key,
                                "title": section.title,
                                "ordinal": section.ordinal,
                            }
                            for section in generated_sections
                        ],
                    )
                    raise
                self._record_llm_generation_completed(
                    "llm_section_repair_completed",
                    section=repaired,
                    llm_task="documentation_section_repair",
                )
                attempt_artifact = self._publish_markdown(
                    run=run,
                    artifact_kind=f"draft_section_markdown_repair_{plan.repair_round}",
                    section_key=repaired.section_key,
                    key=(
                        f"{_attempt_prefix(run)}/sections/"
                        f"{repaired.section_key}.repair-{plan.repair_round}.md"
                    ),
                    markdown=repaired.content_markdown,
                )
                repair_attempts.append(
                    {
                        "repair_round": plan.repair_round,
                        "section_key": repaired.section_key,
                        "findings": [finding.to_dict() for finding in section_plan.findings],
                        "artifact": attempt_artifact,
                        "generation": repaired.generation,
                        "repair_evidence_delta": {
                            "source_ids": [
                                source.get("source_id")
                                for source in (
                                    repair_evidence_delta.prompt_deltas.get(section_plan.section_key)
                                    or {}
                                ).get("sources", [])
                                if isinstance(source, dict)
                            ],
                            "artifact": delta_artifact,
                        },
                    }
                )
                _replace_section(generated_sections, repaired)
                section_artifacts_by_key[repaired.section_key] = self._publish_section_markdown(
                    run,
                    repaired,
                )

            bundle = self._publish_document_bundle(
                run=run,
                generated_sections=generated_sections,
                template_kind=effective_template_kind,
                publication_state="draft",
            )

        final_report = verification_reports[-1]
        verification_report_artifact = self._publish_json(
            run=run,
            artifact_kind="verification_report",
            section_key=None,
            key=f"{_attempt_prefix(run)}/verification_report.schema-v1.json",
            payload=final_report.to_dict(),
        )
        repair_plan_artifact = None
        if repair_plans:
            repair_plan_artifact = self._publish_json(
                run=run,
                artifact_kind="repair_plan",
                section_key=None,
                key=f"{_attempt_prefix(run)}/repair_plan.schema-v1.json",
                payload={
                    "schema_version": 1,
                    "artifact_kind": "repair_plan",
                    "documentation_run_id": run.id,
                    "plans": [plan.to_dict() for plan in repair_plans],
                },
            )
        repair_attempts_artifact = None
        repair_attempts_manifest = None
        if repair_attempts or repair_plans:
            repair_attempts_manifest = build_repair_attempts_manifest(
                documentation_run_id=run.id,
                repository_id=run.repository_id,
                snapshot_id=run.snapshot_id,
                attempts=repair_attempts,
                plans=repair_plans,
                final_report=final_report,
                evidence_delta_artifacts=repair_evidence_delta_artifacts,
            )
            repair_attempts_artifact = self._publish_json(
                run=run,
                artifact_kind="repair_attempts",
                section_key=None,
                key=f"{_attempt_prefix(run)}/repair_attempts.schema-v1.json",
                payload=repair_attempts_manifest,
            )

        draft_manifest = self._build_manifest(
            run=run,
            template_kind=effective_template_kind,
            template_selection=template_selection.to_dict(),
            repository_classification=repository_classification.to_dict(),
            generated_sections=generated_sections,
            section_artifacts_by_key=section_artifacts_by_key,
            bundle=bundle,
            evidence_pack_artifact=evidence_pack_artifact,
            prompt_contract_artifact=prompt_contract_artifact,
            rendered_evidence_pack_artifact=rendered_evidence_pack_artifact,
            verification_summary=final_report.summary(),
            verification_report_artifact=verification_report_artifact,
            repair_summary=(repair_attempts_manifest or {}).get("summary"),
            repair_plan_artifact=repair_plan_artifact,
            repair_attempts_artifact=repair_attempts_artifact,
            publication_state="draft",
        )
        draft_manifest_artifact = self._publish_json(
            run=run,
            artifact_kind="draft_manifest",
            section_key=None,
            key=f"{_attempt_prefix(run)}/manifest.schema-v2.json",
            payload=draft_manifest,
            schema_version=2,
        )

        if final_report.has_hard_errors():
            self._publish_pipeline_trace_safely(run, status="failed")
            raise DocumentationVerificationError(
                "Documentation verification failed after repair attempts.",
                report=final_report.to_dict(),
            )

        final_bundle = self._publish_document_bundle(
            run=run,
            generated_sections=generated_sections,
            template_kind=effective_template_kind,
            publication_state="final",
        )
        pipeline_trace_artifact = self._publish_pipeline_trace_safely(run, status="succeeded")
        manifest = self._build_manifest(
            run=run,
            template_kind=effective_template_kind,
            template_selection=template_selection.to_dict(),
            repository_classification=repository_classification.to_dict(),
            generated_sections=generated_sections,
            section_artifacts_by_key=section_artifacts_by_key,
            bundle=final_bundle,
            evidence_pack_artifact=evidence_pack_artifact,
            prompt_contract_artifact=prompt_contract_artifact,
            rendered_evidence_pack_artifact=rendered_evidence_pack_artifact,
            verification_summary=final_report.summary(),
            verification_report_artifact=verification_report_artifact,
            repair_summary=(repair_attempts_manifest or {}).get("summary"),
            repair_plan_artifact=repair_plan_artifact,
            repair_attempts_artifact=repair_attempts_artifact,
            pipeline_trace_artifact=pipeline_trace_artifact,
            draft_manifest_artifact=draft_manifest_artifact,
            publication_state="final",
        )
        manifest_artifact = self._publish_json(
            run=run,
            artifact_kind="manifest",
            section_key=None,
            key=f"{_run_prefix(run)}/manifest.schema-v2.json",
            payload=manifest,
            schema_version=2,
        )
        bundle = final_bundle
        report_progress(
            "publishing_artifacts",
            92,
            progress_current=len(section_artifacts_by_key) + len(bundle.document_artifacts) + 8,
            progress_total=len(section_artifacts_by_key) + len(bundle.document_artifacts) + 8,
        )

        return DocumentationPlanResult(
            sections=sections,
            summary={
                "scaffold_only": False,
                "template_kind": effective_template_kind,
                "requested_template_kind": run.template_kind,
                "template_selection": template_selection.to_dict(),
                "repository_classification": repository_classification.to_dict(),
                "source_index_run_id": run.source_index_run_id,
                "analysis_artifacts": {
                    kind: {
                        "artifact_id": ref.id,
                        "schema_version": ref.schema_version,
                        "storage_key": ref.storage_key,
                    }
                    for kind, ref in sorted(latest_refs.items())
                    if kind in REQUIRED_ANALYSIS_ARTIFACTS
                },
                "sections_total": len(sections),
                "section_source_counts": {
                    section.section_key: len(section.sources)
                    for section in sections
                },
                "evidence_pack_counts": {
                    section.section_key: len(section.evidence_pack.sources) if section.evidence_pack else 0
                    for section in sections
                },
                "evidence_pack_estimated_tokens": {
                    section.section_key: section.evidence_pack.estimated_tokens if section.evidence_pack else 0
                    for section in sections
                },
                "rendered_evidence_pack_counts": {
                    section.section_key: (
                        len(section.rendered_evidence_pack.sources)
                        if section.rendered_evidence_pack
                        else 0
                    )
                    for section in sections
                },
                "rendered_evidence_pack_estimated_tokens": {
                    section.section_key: (
                        section.rendered_evidence_pack.estimated_tokens
                        if section.rendered_evidence_pack
                        else 0
                    )
                    for section in sections
                },
                "generated_sections_total": len(generated_sections),
                "generated_documents_total": len(bundle.documents),
                "generated_documents": [
                    {
                        "document_key": document.document_key,
                        "title": document.title,
                        "file_name": document.file_name,
                        "section_keys": list(document.section_keys),
                    }
                    for document in bundle.documents
                ],
                "generation_summary": _generation_summary(generated_sections),
                "verification_summary": final_report.summary(),
                "verification_report_artifact": verification_report_artifact,
                "repair_summary": (repair_attempts_manifest or {}).get("summary"),
                "repair_plan_artifact": repair_plan_artifact,
                "repair_attempts_artifact": repair_attempts_artifact,
                "repair_evidence_delta_artifacts": repair_evidence_delta_artifacts,
                "pipeline_trace_artifact": pipeline_trace_artifact,
                "draft_manifest_artifact": draft_manifest_artifact,
                "evidence_pack_artifact": evidence_pack_artifact,
                "rendered_evidence_pack_artifact": rendered_evidence_pack_artifact,
                "prompt_contract_artifact": prompt_contract_artifact,
                "documentation_artifact": bundle.documentation_artifact,
                "document_artifacts": bundle.document_artifacts,
                "manifest_artifact": manifest_artifact,
            },
        )

    def _load_required_artifacts(
        self,
        refs: dict[str, AnalysisArtifactRef],
    ) -> dict[str, Any]:
        missing = [kind for kind in REQUIRED_ANALYSIS_ARTIFACTS if kind not in refs]
        if missing:
            raise ValueError(f"Missing required analysis artifacts: {', '.join(missing)}")

        return {
            kind: self._storage.get_json(ref.storage_key, bucket=ref.storage_bucket)
            for kind, ref in refs.items()
            if kind in REQUIRED_ANALYSIS_ARTIFACTS
        }

    def _publish_section_markdown(
        self,
        run: ClaimedDocumentationRun,
        section: GeneratedSection,
    ) -> dict[str, Any]:
        return self._publish_markdown(
            run=run,
            artifact_kind="draft_section_markdown",
            section_key=section.section_key,
            key=f"{_attempt_prefix(run)}/sections/{section.section_key}.md",
            markdown=section.content_markdown,
        )

    def _publish_document_bundle(
        self,
        *,
        run: ClaimedDocumentationRun,
        generated_sections: list[GeneratedSection],
        template_kind: str,
        publication_state: str,
    ) -> _PublishedDocumentBundle:
        if publication_state not in {"draft", "final"}:
            raise ValueError(f"Unsupported documentation publication_state: {publication_state}")

        prefix = _attempt_prefix(run) if publication_state == "draft" else _run_prefix(run)
        artifact_prefix = "draft_" if publication_state == "draft" else ""
        generated_documents = self._generator.assemble_documents(
            generated_sections,
            template_kind=template_kind,
        )
        document_artifacts: list[dict[str, Any]] = []
        for document in generated_documents:
            document_artifacts.append(
                self._publish_markdown(
                    run=run,
                    artifact_kind=f"{artifact_prefix}{document.artifact_kind}",
                    section_key=None,
                    key=f"{prefix}/{document.file_name}",
                    markdown=document.content_markdown,
                )
            )

        document_markdown = self._generator.assemble_index_document(
            generated_documents,
            sections=generated_sections,
            template_kind=template_kind,
        )
        documentation_artifact = self._publish_markdown(
            run=run,
            artifact_kind=f"{artifact_prefix}documentation_markdown",
            section_key=None,
            key=f"{prefix}/documentation.md",
            markdown=document_markdown,
        )
        return _PublishedDocumentBundle(
            documents=generated_documents,
            document_artifacts=document_artifacts,
            documentation_artifact=documentation_artifact,
        )

    def _build_manifest(
        self,
        *,
        run: ClaimedDocumentationRun,
        template_kind: str,
        template_selection: dict[str, Any],
        repository_classification: dict[str, Any],
        generated_sections: list[GeneratedSection],
        section_artifacts_by_key: dict[str, dict[str, Any]],
        bundle: _PublishedDocumentBundle,
        evidence_pack_artifact: dict[str, Any],
        prompt_contract_artifact: dict[str, Any],
        rendered_evidence_pack_artifact: dict[str, Any],
        verification_summary: dict[str, Any] | None = None,
        verification_report_artifact: dict[str, Any] | None = None,
        repair_summary: dict[str, Any] | None = None,
        repair_plan_artifact: dict[str, Any] | None = None,
        repair_attempts_artifact: dict[str, Any] | None = None,
        pipeline_trace_artifact: dict[str, Any] | None = None,
        draft_manifest_artifact: dict[str, Any] | None = None,
        publication_state: str = "draft",
    ) -> dict[str, Any]:
        return self._generator.build_manifest(
            documentation_run_id=run.id,
            repository_id=run.repository_id,
            snapshot_id=run.snapshot_id,
            attempt=run.attempt,
            publication_state=publication_state,
            template_kind=template_kind,
            requested_template_kind=run.template_kind,
            template_selection=template_selection,
            repository_classification=repository_classification,
            sections=generated_sections,
            section_artifacts=[
                section_artifacts_by_key[section.section_key]
                for section in generated_sections
            ],
            documents=bundle.documents,
            document_artifacts=bundle.document_artifacts,
            documentation_artifact=bundle.documentation_artifact,
            evidence_pack_artifact=evidence_pack_artifact,
            prompt_contract_artifact=prompt_contract_artifact,
            rendered_evidence_pack_artifact=rendered_evidence_pack_artifact,
            verification_summary=verification_summary,
            verification_report_artifact=verification_report_artifact,
            repair_summary=repair_summary,
            repair_plan_artifact=repair_plan_artifact,
            repair_attempts_artifact=repair_attempts_artifact,
            pipeline_trace_artifact=pipeline_trace_artifact,
            draft_manifest_artifact=draft_manifest_artifact,
        )

    def _publish_markdown(
        self,
        *,
        run: ClaimedDocumentationRun,
        artifact_kind: str,
        section_key: str | None,
        key: str,
        markdown: str,
        record_trace: bool = True,
    ) -> dict[str, Any]:
        return self._publish_bytes(
            run=run,
            artifact_kind=artifact_kind,
            section_key=section_key,
            key=key,
            payload=markdown.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
            format="markdown",
            record_trace=record_trace,
        )

    def _publish_json(
        self,
        *,
        run: ClaimedDocumentationRun,
        artifact_kind: str,
        section_key: str | None,
        key: str,
        payload: dict[str, Any],
        schema_version: int = 1,
        record_trace: bool = True,
    ) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2, default=str).encode("utf-8")
        return self._publish_bytes(
            run=run,
            artifact_kind=artifact_kind,
            section_key=section_key,
            key=key,
            payload=data,
            content_type="application/json; charset=utf-8",
            format="json",
            schema_version=schema_version,
            record_trace=record_trace,
        )

    def _publish_bytes(
        self,
        *,
        run: ClaimedDocumentationRun,
        artifact_kind: str,
        section_key: str | None,
        key: str,
        payload: bytes,
        content_type: str,
        format: str,
        schema_version: int = 1,
        record_trace: bool = True,
    ) -> dict[str, Any]:
        checksum = hashlib.sha256(payload).hexdigest()
        self._storage.put_bytes(key, payload, content_type)
        artifact = self._repository_service.register_documentation_artifact(
            run.id,
            {
                "artifact_kind": artifact_kind,
                "section_key": section_key,
                "attempt": run.attempt,
                "storage_bucket": self._storage.bucket,
                "storage_key": key,
                "content_type": content_type,
                "format": format,
                "checksum_sha256": checksum,
                "size_bytes": len(payload),
                "schema_version": schema_version,
            },
        )
        summary = {
            "artifact_kind": artifact_kind,
            "section_key": section_key,
            "attempt": run.attempt,
            "storage_key": key,
            "schema_version": schema_version,
            "size_bytes": len(payload),
            "checksum_sha256": checksum,
        }
        self._published_artifacts.append(summary)
        logger.info(
            (
                "Documentation artifact published documentation_run_id=%s attempt=%s "
                "artifact_kind=%s section_key=%s storage_key=%s schema_version=%s "
                "size_bytes=%s checksum_sha256=%s"
            ),
            run.id,
            run.attempt,
            artifact_kind,
            section_key,
            key,
            schema_version,
            len(payload),
            checksum,
        )
        if record_trace:
            self._record_trace("artifact_published", **summary)
        return artifact

    def _new_trace(self, run: ClaimedDocumentationRun) -> PipelineTrace | None:
        if not self._pipeline_trace_enabled:
            return None
        return PipelineTrace(
            documentation_run_id=run.id,
            repository_id=run.repository_id,
            snapshot_id=run.snapshot_id,
            attempt=run.attempt,
            requested_template_kind=run.template_kind,
        )

    def _record_trace(self, event_type: str, **fields: Any) -> None:
        if self._trace is not None:
            self._trace.record(event_type, **fields)

    def _record_attempt_state(self, run: ClaimedDocumentationRun) -> None:
        artifacts = self._repository_service.list_documentation_artifacts(run.id)
        previous_attempts = sorted(
            {
                artifact.attempt
                for artifact in artifacts
                if artifact.attempt < run.attempt
            }
        )
        current_attempt_artifacts = [
            artifact
            for artifact in artifacts
            if artifact.attempt == run.attempt
        ]
        logger.info(
            (
                "Documentation attempt state loaded documentation_run_id=%s attempt=%s "
                "previous_attempts=%s current_attempt_artifacts=%s resume_strategy=%s"
            ),
            run.id,
            run.attempt,
            previous_attempts,
            len(current_attempt_artifacts),
            "clean_attempt",
        )
        self._record_trace(
            "attempt_state_loaded",
            attempt=run.attempt,
            previous_attempts=previous_attempts,
            previous_attempts_total=len(previous_attempts),
            current_attempt_artifacts_total=len(current_attempt_artifacts),
            resume_strategy="clean_attempt",
            resume_reason="attempt artifacts are isolated; safe section reuse is deferred",
        )

    def _record_template_selection(
        self,
        *,
        requested_template_kind: str | None,
        effective_template_kind: str,
        template_selection: dict[str, Any],
        repository_classification: dict[str, Any],
    ) -> None:
        if self._trace is not None:
            self._trace.set_template_context(
                effective_template_kind=effective_template_kind,
                template_selection=template_selection,
                repository_classification=repository_classification,
            )
        classification_kind = repository_classification.get("repository_kind")
        confidence = repository_classification.get("confidence")
        top_signals = repository_classification.get("signals") or []
        reason = template_selection.get("reason")
        logger.info(
            (
                "Documentation template selected requested_template_kind=%s "
                "effective_template_kind=%s repository_kind=%s confidence=%s "
                "reason=%s top_signals=%s"
            ),
            requested_template_kind,
            effective_template_kind,
            classification_kind,
            confidence,
            reason,
            top_signals[:5] if isinstance(top_signals, list) else top_signals,
        )
        self._record_trace(
            "template_selected",
            requested_template_kind=requested_template_kind,
            effective_template_kind=effective_template_kind,
            repository_kind=classification_kind,
            confidence=confidence,
            reason=reason,
            top_signals=top_signals[:5] if isinstance(top_signals, list) else top_signals,
        )

    def _record_llm_generation_completed(
        self,
        event_type: str,
        *,
        section: GeneratedSection,
        llm_task: str,
    ) -> None:
        generation = section.generation or {}
        retry_errors = generation.get("llm_retry_errors") or []
        self._record_trace(
            event_type,
            llm_task=llm_task,
            section_key=section.section_key,
            provider=generation.get("provider"),
            model=generation.get("model"),
            response_id=generation.get("response_id"),
            finish_reason=generation.get("finish_reason"),
            prompt_tokens=generation.get("prompt_tokens"),
            completion_tokens=generation.get("completion_tokens"),
            total_tokens=generation.get("total_tokens"),
            latency_ms=generation.get("latency_ms"),
            attempts_total=generation.get("llm_attempts_total"),
            retry_errors_total=len(retry_errors) if isinstance(retry_errors, list) else 0,
            quality_status=generation.get("quality_status"),
            warnings=generation.get("warnings"),
        )

    def _record_verification_completed(self, report: VerificationReport) -> None:
        summary = report.summary()
        self._record_trace(
            "verification_completed",
            stage="verifying_documentation",
            repair_round=report.repair_round,
            status=report.status,
            judge_calls_total=summary.get("judge_calls_total"),
            errors_total=summary.get("errors_total"),
            warnings_total=summary.get("warnings_total"),
            repairable_errors_total=summary.get("repairable_errors_total"),
        )
        for call in report.judge_calls:
            retry_errors = call.retry_errors or []
            self._record_trace(
                "llm_judge_completed",
                stage="verifying_documentation",
                llm_task="documentation_judge",
                scope=call.scope,
                provider=call.provider,
                model=call.model,
                response_id=call.response_id,
                finish_reason=call.finish_reason,
                prompt_tokens=call.prompt_tokens,
                completion_tokens=call.completion_tokens,
                total_tokens=call.total_tokens,
                latency_ms=call.latency_ms,
                attempts_total=call.attempts_total,
                retry_errors_total=len(retry_errors),
                response_format=call.response_format,
            )

    def _set_failure_context(self, **fields: Any) -> None:
        self._failure_context = fields

    def _publish_pipeline_trace_safely(
        self,
        run: ClaimedDocumentationRun,
        *,
        status: str,
    ) -> dict[str, Any] | None:
        if self._trace is None:
            return None
        try:
            self._record_trace("pipeline_finished", status=status)
            self._record_trace("pipeline_trace_publishing", status=status)
            artifact = self._publish_json(
                run=run,
                artifact_kind="pipeline_trace",
                section_key=None,
                key=(
                    f"{_attempt_prefix(run)}/pipeline_trace.schema-v1.json"
                ),
                payload=self._trace.to_dict(status=status),
                record_trace=False,
            )
            self._pipeline_trace_published = True
            return artifact
        except Exception:
            logger.warning(
                "Could not publish pipeline trace for documentation_run=%s",
                run.id,
                exc_info=True,
            )
            return None

    def _publish_pipeline_error_safely(
        self,
        *,
        run: ClaimedDocumentationRun,
        stage: str,
        error: Exception,
        section_key: str | None = None,
        repair_round: int | None = None,
        completed_sections: list[dict[str, Any]] | None = None,
    ) -> None:
        if isinstance(error, DocumentationVerificationError):
            if not self._pipeline_trace_published:
                self._publish_pipeline_trace_safely(run, status="failed")
            return

        failure = error_payload(error)
        self._record_trace(
            "pipeline_failed",
            stage=stage,
            section_key=section_key,
            repair_round=repair_round,
            error=failure,
        )
        payload = {
            "schema_version": 1,
            "artifact_kind": "pipeline_error",
            "documentation_run_id": run.id,
            "repository_id": run.repository_id,
            "snapshot_id": run.snapshot_id,
            "attempt": run.attempt,
            "requested_template_kind": run.template_kind,
            "effective_template_kind": self._trace.effective_template_kind if self._trace else None,
            "stage": stage,
            "section_key": section_key,
            "repair_round": repair_round,
            "error": failure,
            "completed_sections": completed_sections or [],
            "published_artifacts": list(self._published_artifacts),
            "trace_summary": self._trace.summary() if self._trace else None,
        }
        try:
            self._publish_json(
                run=run,
                artifact_kind="pipeline_error",
                section_key=section_key,
                key=(
                    f"{_attempt_prefix(run)}/pipeline_error.schema-v1.json"
                ),
                payload=payload,
            )
        except Exception:
            logger.warning(
                "Could not publish pipeline error artifact for documentation_run=%s",
                run.id,
                exc_info=True,
            )
        self._publish_pipeline_trace_safely(run, status="failed")

    def _publish_generation_error_safely(
        self,
        *,
        run: ClaimedDocumentationRun,
        contract: SectionPromptContract,
        template_kind: str,
        error: Exception,
        completed_sections: list[GeneratedSection],
    ) -> None:
        try:
            self._publish_json(
                run=run,
                artifact_kind="generation_error_manifest",
                section_key=None,
                key=(
                    f"{_attempt_prefix(run)}/generation_errors.schema-v1.json"
                ),
                payload={
                    "schema_version": 1,
                    "artifact_kind": "generation_error_manifest",
                    "documentation_run_id": run.id,
                    "repository_id": run.repository_id,
                    "snapshot_id": run.snapshot_id,
                    "attempt": run.attempt,
                    "template_kind": template_kind,
                    "requested_template_kind": run.template_kind,
                    "completed_sections": [
                        {
                            "section_key": section.section_key,
                            "title": section.title,
                            "ordinal": section.ordinal,
                        }
                        for section in completed_sections
                    ],
                    "errors": [_section_error(contract, error)],
                },
            )
        except Exception:
            logger.warning(
                "Could not publish generation error manifest for documentation_run=%s",
                run.id,
                exc_info=True,
            )


def _latest_by_kind(refs: list[AnalysisArtifactRef]) -> dict[str, AnalysisArtifactRef]:
    latest: dict[str, AnalysisArtifactRef] = {}
    for ref in refs:
        current = latest.get(ref.artifact_kind)
        if current is None or ref.schema_version > current.schema_version:
            latest[ref.artifact_kind] = ref
    return latest


def _generation_summary(sections: list[GeneratedSection]) -> dict[str, Any]:
    metadata = [section.generation or {} for section in sections]
    return {
        "provider": _same_or_list(item.get("provider") for item in metadata),
        "model": _same_or_list(item.get("model") for item in metadata),
        "sections": {
            section.section_key: section.generation or {}
            for section in sections
        },
        "prompt_tokens": _sum_int(item.get("prompt_tokens") for item in metadata),
        "completion_tokens": _sum_int(item.get("completion_tokens") for item in metadata),
        "total_tokens": _sum_int(item.get("total_tokens") for item in metadata),
        "latency_ms": _sum_int(item.get("latency_ms") for item in metadata),
        "finish_reasons": {
            section.section_key: (section.generation or {}).get("finish_reason")
            for section in sections
        },
        "quality_statuses": {
            section.section_key: (section.generation or {}).get("quality_status")
            for section in sections
        },
        "degraded_sections": [
            section.section_key
            for section in sections
            if (section.generation or {}).get("quality_status") == "degraded"
        ],
        "warnings": {
            section.section_key: (section.generation or {}).get("warnings")
            for section in sections
            if (section.generation or {}).get("warnings")
        },
    }


def _section_error(contract: SectionPromptContract, error: Exception) -> dict[str, Any]:
    return {
        "section_key": contract.section_key,
        "title": contract.title,
        "ordinal": contract.ordinal,
        "error_type": error.__class__.__name__,
        "error_code": getattr(error, "error_code", "section_generation_failed"),
        "retryable": bool(getattr(error, "retryable", False)),
        "message": _truncate(str(error), 2000),
    }


def _same_or_list(values: Any) -> Any:
    unique = sorted({value for value in values if value is not None})
    if not unique:
        return None
    if len(unique) == 1:
        return unique[0]
    return unique


def _sum_int(values: Any) -> int | None:
    total = 0
    seen = False
    for value in values:
        if value is None:
            continue
        try:
            total += int(value)
        except (TypeError, ValueError):
            continue
        seen = True
    return total if seen else None


def _truncate(value: str, max_length: int) -> str:
    if not value:
        return ""
    return value if len(value) <= max_length else value[:max_length]


def _run_prefix(run: ClaimedDocumentationRun) -> str:
    return (
        f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}"
        f"/documentation-runs/{run.id}"
    )


def _attempt_prefix(run: ClaimedDocumentationRun) -> str:
    return f"{_run_prefix(run)}/attempts/{run.attempt}"


def _section_by_key(
    sections: list[GeneratedSection],
    section_key: str,
) -> GeneratedSection | None:
    return next((section for section in sections if section.section_key == section_key), None)


def _replace_section(
    sections: list[GeneratedSection],
    replacement: GeneratedSection,
) -> None:
    for index, section in enumerate(sections):
        if section.section_key == replacement.section_key:
            sections[index] = replacement
            return
    sections.append(replacement)


def _attach_prompt_contracts(
    sections: list[SectionEvidence],
    *,
    template_kind: str,
    output_language: str,
) -> list[SectionPromptContract]:
    contracts: list[SectionPromptContract] = []
    for section in sections:
        contract = build_section_prompt_contract(
            section,
            template_kind=template_kind,
            output_language=output_language,
        )
        section.prompt_contract = contract.to_dict()
        contracts.append(contract)
    return contracts


def _replace_prompt_contracts(
    contracts: list[SectionPromptContract],
    updates: dict[str, SectionPromptContract],
) -> list[SectionPromptContract]:
    return [
        updates.get(contract.section_key, contract)
        for contract in contracts
    ]


def _evidence_packs(sections: list[SectionEvidence]) -> list[EvidencePack]:
    packs: list[EvidencePack] = []
    for section in sections:
        if section.evidence_pack is None:
            raise ValueError(f"Section {section.section_key} has no evidence pack.")
        packs.append(section.evidence_pack)
    return packs


def _rendered_evidence_packs(sections: list[SectionEvidence]) -> list[RenderedEvidencePack]:
    packs: list[RenderedEvidencePack] = []
    for section in sections:
        if section.rendered_evidence_pack is None:
            raise ValueError(f"Section {section.section_key} has no rendered evidence pack.")
        packs.append(section.rendered_evidence_pack)
    return packs
