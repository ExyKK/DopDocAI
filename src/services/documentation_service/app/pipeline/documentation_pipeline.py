from dataclasses import dataclass
from typing import Any

from app.infra.object_storage import ObjectStorageClient
from app.infra.repository_service_client import AnalysisArtifactRef, RepositoryServiceClient
from app.infra.retrieval_client import RetrievalClient
from app.pipeline.evidence import EvidencePlanner, SectionEvidence
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


class DocumentationPlanningPipeline:
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

    def build_section_plan(self, run: ClaimedDocumentationRun) -> DocumentationPlanResult:
        refs = self._repository_service.list_analysis_artifacts(run.repository_id, run.snapshot_id)
        latest_refs = _latest_by_kind(refs)
        artifacts = self._load_required_artifacts(latest_refs)
        templates = get_section_templates(run.template_kind)

        sections = self._planner.plan(
            snapshot_id=run.snapshot_id,
            templates=templates,
            artifacts=artifacts,
        )
        self._repository_service.replace_documentation_sections(
            run.id,
            [section.to_request() for section in sections],
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


def _latest_by_kind(refs: list[AnalysisArtifactRef]) -> dict[str, AnalysisArtifactRef]:
    latest: dict[str, AnalysisArtifactRef] = {}
    for ref in refs:
        current = latest.get(ref.artifact_kind)
        if current is None or ref.schema_version > current.schema_version:
            latest[ref.artifact_kind] = ref
    return latest
