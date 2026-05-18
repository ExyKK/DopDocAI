import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.infra.object_storage import ObjectStorageClient
from app.infra.repository_service_client import AnalysisArtifactRef, RepositoryServiceClient
from app.infra.retrieval_client import RetrievalClient
from app.pipeline.evidence import EvidencePlanner, SectionEvidence
from app.pipeline.generator import DeveloperHandbookGenerator
from app.pipeline.templates import get_section_templates
from app.worker.job_store import ClaimedDocumentationRun


REQUIRED_ANALYSIS_ARTIFACTS = (
    "project_model",
    "package_graph",
    "config_inventory",
    "commit_log",
)


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
    ):
        self._repository_service = repository_service
        self._storage = storage
        self._planner = EvidencePlanner(retrieval)
        self._generator = DeveloperHandbookGenerator()

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
        templates = get_section_templates(run.template_kind)

        report_progress("planning_sections", 35, progress_total=len(templates))
        sections = self._planner.plan(
            snapshot_id=run.snapshot_id,
            templates=templates,
            artifacts=artifacts,
        )

        report_progress("retrieving_evidence", 65, progress_current=len(sections), progress_total=len(sections))
        self._repository_service.replace_documentation_sections(
            run.id,
            [section.to_request() for section in sections],
        )

        report_progress("generating_sections", 78, progress_current=0, progress_total=len(sections))
        generated_sections = self._generator.generate_sections(sections)

        section_artifacts: list[dict[str, Any]] = []
        for index, section in enumerate(generated_sections, start=1):
            artifact = self._publish_markdown(
                run=run,
                artifact_kind="section_markdown",
                section_key=section.section_key,
                key=f"repositories/{run.repository_id}/snapshots/{run.snapshot_id}/documentation-runs/{run.id}/sections/{section.section_key}.md",
                markdown=section.content_markdown,
            )
            section_artifacts.append(artifact)
            report_progress("generating_sections", 78, progress_current=index, progress_total=len(sections))

        document_markdown = self._generator.assemble_document(generated_sections)
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
            template_kind=run.template_kind,
            sections=generated_sections,
            section_artifacts=section_artifacts,
            documentation_artifact=documentation_artifact,
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
            progress_current=len(section_artifacts) + 2,
            progress_total=len(section_artifacts) + 2,
        )

        return DocumentationPlanResult(
            sections=sections,
            summary={
                "scaffold_only": False,
                "template_kind": run.template_kind,
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
                "generated_sections_total": len(generated_sections),
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


def _latest_by_kind(refs: list[AnalysisArtifactRef]) -> dict[str, AnalysisArtifactRef]:
    latest: dict[str, AnalysisArtifactRef] = {}
    for ref in refs:
        current = latest.get(ref.artifact_kind)
        if current is None or ref.schema_version > current.schema_version:
            latest[ref.artifact_kind] = ref
    return latest
