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
from app.pipeline.generator import DeveloperHandbookGenerator, GeneratedSection
from app.pipeline.llm_generation import LlmSectionGenerator
from app.pipeline.prompt_contract import (
    SectionPromptContract,
    build_prompt_contract_manifest,
    build_section_prompt_contract,
)
from app.pipeline.rendered_evidence import (
    RenderedEvidencePack,
    build_rendered_evidence_pack_manifest,
)
from app.pipeline.templates import get_section_templates, select_documentation_template
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
    ):
        self._repository_service = repository_service
        self._storage = storage
        self._planner = EvidencePlanner(retrieval, budget=evidence_pack_budget)
        self._generator = DeveloperHandbookGenerator()
        self._section_generator = LlmSectionGenerator(llm_provider)
        self._prompt_output_language = prompt_output_language

    def build_developer_handbook(
        self,
        run: ClaimedDocumentationRun,
        *,
        report_progress,
    ) -> DocumentationPlanResult:
        report_progress("loading_project_model", 20)
        refs = self._repository_service.list_analysis_artifacts(run.repository_id, run.snapshot_id)
        latest_refs = _latest_by_kind(refs)
        artifacts = self._load_required_artifacts(latest_refs)
        repository_classification = classify_repository(artifacts)
        template_selection = select_documentation_template(run.template_kind, repository_classification)
        effective_template_kind = template_selection.effective_template_kind
        templates = get_section_templates(effective_template_kind)

        report_progress("planning_sections", 35, progress_total=len(templates))
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
        self._repository_service.replace_documentation_sections(
            run.id,
            [section.to_request() for section in sections],
        )

        evidence_pack_artifact = self._publish_json(
            run=run,
            artifact_kind="evidence_pack_manifest",
            section_key=None,
            key=f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}/documentation-runs/{run.id}/evidence_packs.schema-v1.json",
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
            key=f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}/documentation-runs/{run.id}/prompt_contracts.schema-v1.json",
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
            key=(
                f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}/documentation-runs/{run.id}"
                "/rendered_evidence_packs.schema-v1.json"
            ),
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
        section_artifacts: list[dict[str, Any]] = []
        for index, contract in enumerate(prompt_contracts, start=1):
            try:
                generated = self._section_generator.generate_section(contract)
            except Exception as exc:
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
            artifact = self._publish_markdown(
                run=run,
                artifact_kind="section_markdown",
                section_key=section.section_key,
                key=f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}/documentation-runs/{run.id}/sections/{section.section_key}.md",
                markdown=section.content_markdown,
            )
            section_artifacts.append(artifact)
            report_progress("generating_sections", 78, progress_current=index, progress_total=len(sections))

        document_markdown = self._generator.assemble_document(
            generated_sections,
            template_kind=effective_template_kind,
        )
        documentation_artifact = self._publish_markdown(
            run=run,
            artifact_kind="documentation_markdown",
            section_key=None,
            key=f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}/documentation-runs/{run.id}/documentation.md",
            markdown=document_markdown,
        )

        manifest = self._generator.build_manifest(
            documentation_run_id=run.id,
            repository_id=run.repository_id,
            snapshot_id=run.snapshot_id,
            template_kind=effective_template_kind,
            requested_template_kind=run.template_kind,
            template_selection=template_selection.to_dict(),
            repository_classification=repository_classification.to_dict(),
            sections=generated_sections,
            section_artifacts=section_artifacts,
            documentation_artifact=documentation_artifact,
            evidence_pack_artifact=evidence_pack_artifact,
            prompt_contract_artifact=prompt_contract_artifact,
            rendered_evidence_pack_artifact=rendered_evidence_pack_artifact,
        )
        manifest_artifact = self._publish_json(
            run=run,
            artifact_kind="manifest",
            section_key=None,
            key=f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}/documentation-runs/{run.id}/manifest.schema-v1.json",
            payload=manifest,
        )
        report_progress(
            "publishing_artifacts",
            92,
            progress_current=len(section_artifacts) + 5,
            progress_total=len(section_artifacts) + 5,
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
                "generation_summary": _generation_summary(generated_sections),
                "evidence_pack_artifact": evidence_pack_artifact,
                "rendered_evidence_pack_artifact": rendered_evidence_pack_artifact,
                "prompt_contract_artifact": prompt_contract_artifact,
                "documentation_artifact": documentation_artifact,
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

    def _publish_markdown(
        self,
        *,
        run: ClaimedDocumentationRun,
        artifact_kind: str,
        section_key: str | None,
        key: str,
        markdown: str,
    ) -> dict[str, Any]:
        return self._publish_bytes(
            run=run,
            artifact_kind=artifact_kind,
            section_key=section_key,
            key=key,
            payload=markdown.encode("utf-8"),
            content_type="text/markdown; charset=utf-8",
            format="markdown",
        )

    def _publish_json(
        self,
        *,
        run: ClaimedDocumentationRun,
        artifact_kind: str,
        section_key: str | None,
        key: str,
        payload: dict[str, Any],
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
    ) -> dict[str, Any]:
        checksum = hashlib.sha256(payload).hexdigest()
        self._storage.put_bytes(key, payload, content_type)
        return self._repository_service.register_documentation_artifact(
            run.id,
            {
                "artifact_kind": artifact_kind,
                "section_key": section_key,
                "storage_bucket": self._storage.bucket,
                "storage_key": key,
                "content_type": content_type,
                "format": format,
                "checksum_sha256": checksum,
                "size_bytes": len(payload),
                "schema_version": 1,
            },
        )

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
                    f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}"
                    f"/documentation-runs/{run.id}/generation_errors.schema-v1.json"
                ),
                payload={
                    "schema_version": 1,
                    "artifact_kind": "generation_error_manifest",
                    "documentation_run_id": run.id,
                    "repository_id": run.repository_id,
                    "snapshot_id": run.snapshot_id,
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
