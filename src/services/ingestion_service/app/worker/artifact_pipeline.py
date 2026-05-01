from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from app.artifacts.file_inventory import build_file_inventory_artifact
from app.artifacts.go_symbols import build_go_symbols_artifact
from app.artifacts.models import BuiltAnalysisArtifact
from app.artifacts.package_graph import build_package_graph_artifact
from app.infra.treesitter_client import TreeSitterManager


class ProgressReporter(Protocol):
    def __call__(
        self,
        stage: str,
        progress_pct: int,
        message: str,
        *,
        progress_current: int = 0,
        progress_total: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        pass


class ArtifactStorage(Protocol):
    bucket: str

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        pass


class AnalysisArtifactRegistrar(Protocol):
    def upsert_analysis_artifact(
        self,
        repository_id: str,
        snapshot_id: str,
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        pass


@dataclass(frozen=True)
class IndexAnalysisArtifacts:
    artifacts: tuple[BuiltAnalysisArtifact, ...]
    stats: dict[str, Any]
    files_processed: int
    symbols_total: int
    finalizing_payload: dict[str, Any]


def build_index_analysis_artifacts(
    repo_path: str | Path,
    *,
    repository_id: str,
    snapshot_id: str,
    snapshot_metadata: dict[str, Any],
    treesitter: TreeSitterManager,
    report_progress: ProgressReporter,
    ensure_alive: Callable[[], None],
) -> IndexAnalysisArtifacts:
    report_progress(
        "scanning_files",
        85,
        "Building deterministic file inventory.",
        progress_current=snapshot_metadata["files_total"],
        progress_total=snapshot_metadata["files_total"],
        payload={"snapshot_id": snapshot_id},
    )
    file_inventory_artifact = build_file_inventory_artifact(
        repo_path,
        repository_id=repository_id,
        snapshot_id=snapshot_id,
        snapshot_metadata=snapshot_metadata,
    )
    ensure_alive()

    report_progress(
        "parsing",
        90,
        "Extracting Go symbols from resolved snapshot.",
        progress_current=snapshot_metadata["go_files_total"],
        progress_total=snapshot_metadata["go_files_total"],
        payload={"snapshot_id": snapshot_id, "go_files_total": snapshot_metadata["go_files_total"]},
    )
    go_symbols_artifact = build_go_symbols_artifact(
        repo_path,
        repository_id=repository_id,
        snapshot_id=snapshot_id,
        snapshot_metadata=snapshot_metadata,
        treesitter=treesitter,
    )
    ensure_alive()

    report_progress(
        "parsing",
        92,
        "Building Go package import graph.",
        progress_current=snapshot_metadata["go_files_total"],
        progress_total=snapshot_metadata["go_files_total"],
        payload={"snapshot_id": snapshot_id, "go_symbols_artifact": go_symbols_artifact.storage_key},
    )
    package_graph_artifact = build_package_graph_artifact(
        repo_path,
        repository_id=repository_id,
        snapshot_id=snapshot_id,
        snapshot_metadata=snapshot_metadata,
        go_symbols_artifact=go_symbols_artifact,
    )
    ensure_alive()

    artifacts = (file_inventory_artifact, go_symbols_artifact, package_graph_artifact)
    package_graph_summary = package_graph_artifact.summary or {}
    stats = {
        "pipeline": "file_inventory_go_symbols_and_package_graph",
        "snapshot_id": snapshot_id,
        "branch_name": snapshot_metadata["branch_name"],
        "commit_sha": snapshot_metadata["commit_sha"],
        "tree_hash": snapshot_metadata["tree_hash"],
        "files_total": snapshot_metadata["files_total"],
        "go_files_total": snapshot_metadata["go_files_total"],
        "readme_files_total": snapshot_metadata["readme_files_total"],
        "bytes_total": snapshot_metadata["bytes_total"],
        "symbols_total": go_symbols_artifact.summary["symbols_total"] if go_symbols_artifact.summary else 0,
        "packages_total": package_graph_summary.get("packages_total", 0),
        "package_edges_total": package_graph_summary.get("edges_total", 0),
        "entrypoint_packages_total": package_graph_summary.get("entrypoint_packages_total", 0),
        "artifacts": _artifact_manifest(artifacts),
    }

    return IndexAnalysisArtifacts(
        artifacts=artifacts,
        stats=stats,
        files_processed=snapshot_metadata["files_total"],
        symbols_total=go_symbols_artifact.row_count,
        finalizing_payload={
            "snapshot_id": snapshot_id,
            "artifacts_total": len(artifacts),
            "symbols_total": go_symbols_artifact.row_count,
            "packages_total": package_graph_summary.get("packages_total", 0),
            "package_edges_total": package_graph_summary.get("edges_total", 0),
        },
    )


def publish_analysis_artifacts(
    *,
    storage: ArtifactStorage,
    repository_service: AnalysisArtifactRegistrar,
    repository_id: str,
    snapshot_id: str,
    index_run_id: str,
    artifacts: tuple[BuiltAnalysisArtifact, ...],
    report_progress: ProgressReporter,
    ensure_alive: Callable[[], None],
) -> None:
    report_progress(
        "publishing_artifacts",
        93,
        "Publishing analysis artifacts.",
        progress_current=0,
        progress_total=len(artifacts),
        payload={
            "snapshot_id": snapshot_id,
            "artifacts": [
                {
                    "artifact_kind": artifact.artifact_kind,
                    "storage_key": artifact.storage_key,
                }
                for artifact in artifacts
            ],
        },
    )

    for index, artifact in enumerate(artifacts, start=1):
        storage.put_bytes(
            key=artifact.storage_key,
            data=artifact.payload,
            content_type=artifact.content_type,
        )
        ensure_alive()

        repository_service.upsert_analysis_artifact(
            repository_id,
            snapshot_id,
            {
                "produced_by_index_run_id": index_run_id,
                "artifact_kind": artifact.artifact_kind,
                "storage_bucket": storage.bucket,
                "storage_key": artifact.storage_key,
                "content_type": artifact.content_type,
                "format": artifact.format,
                "checksum_sha256": artifact.checksum_sha256,
                "size_bytes": artifact.size_bytes,
                "row_count": artifact.row_count,
                "schema_version": artifact.schema_version,
            },
        )
        ensure_alive()

        report_progress(
            "publishing_artifacts",
            _publish_progress_pct(index),
            f"Published {artifact.artifact_kind} artifact.",
            progress_current=index,
            progress_total=len(artifacts),
            payload={
                "artifact_kind": artifact.artifact_kind,
                "storage_key": artifact.storage_key,
            },
        )
        ensure_alive()


def _artifact_manifest(artifacts: tuple[BuiltAnalysisArtifact, ...]) -> list[dict[str, Any]]:
    return [
        {
            "artifact_kind": artifact.artifact_kind,
            "schema_version": artifact.schema_version,
            "row_count": artifact.row_count,
        }
        for artifact in artifacts
    ]


def _publish_progress_pct(index: int) -> int:
    return min(97, 93 + index)
