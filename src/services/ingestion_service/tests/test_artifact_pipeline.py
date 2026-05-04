import json
from pathlib import Path
from typing import Any

import pytest
from git import Actor, Repo

from app.artifacts.models import BuiltAnalysisArtifact
from app.infra.treesitter_client import TreeSitterManager
from app.worker.artifact_pipeline import build_index_analysis_artifacts, publish_analysis_artifacts


def test_build_index_analysis_artifacts_returns_manifest_stats_and_payloads(tmp_path: Path) -> None:
    _write_text(
        tmp_path / "go.mod",
        """module github.com/acme/project

go 1.22
""",
    )
    _write_text(
        tmp_path / "cmd" / "api" / "main.go",
        """package main

import "github.com/acme/project/internal/service"

func main() {
    _ = service.New()
}
""",
    )
    _write_text(
        tmp_path / "internal" / "service" / "service.go",
        """package service

func New() Service {
    return Service{}
}

type Service struct{}
""",
    )

    repo = Repo.init(tmp_path)
    _commit_all(repo, tmp_path)

    commit = repo.head.commit
    metadata = {
        "branch_name": "main",
        "commit_sha": commit.hexsha.lower(),
        "tree_hash": commit.tree.hexsha.lower(),
        "files_total": 3,
        "go_files_total": 2,
        "readme_files_total": 0,
        "bytes_total": sum(
            path.stat().st_size
            for path in tmp_path.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ),
    }

    progress_events: list[dict[str, Any]] = []
    alive_checks = 0

    def report_progress(
        stage: str,
        progress_pct: int,
        message: str,
        *,
        progress_current: int = 0,
        progress_total: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        progress_events.append(
            {
                "stage": stage,
                "progress_pct": progress_pct,
                "message": message,
                "progress_current": progress_current,
                "progress_total": progress_total,
                "payload": payload,
            }
        )

    def ensure_alive() -> None:
        nonlocal alive_checks
        alive_checks += 1

    result = build_index_analysis_artifacts(
        tmp_path,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        snapshot_metadata=metadata,
        treesitter=TreeSitterManager(),
        report_progress=report_progress,
        ensure_alive=ensure_alive,
    )

    assert [artifact.artifact_kind for artifact in result.artifacts] == [
        "file_inventory",
        "go_symbols",
        "package_graph",
        "config_inventory",
        "project_model",
        "commit_log",
    ]
    assert result.files_processed == 3
    assert result.symbols_total == 3
    assert (
        result.stats["pipeline"]
        == "file_inventory_go_symbols_package_graph_config_inventory_project_model_and_commit_log"
    )
    assert result.stats["packages_total"] == 2
    assert result.stats["package_edges_total"] == 1
    assert result.stats["config_items_total"] == 0
    assert result.stats["external_integrations_total"] == 0
    assert result.stats["http_surface_detected"] is False
    assert result.stats["commits_total"] == 1
    assert result.stats["touched_files_total"] == 3
    assert result.stats["touched_packages_total"] == 2
    assert result.stats["artifacts"] == [
        {"artifact_kind": "file_inventory", "row_count": 3, "schema_version": 1},
        {"artifact_kind": "go_symbols", "row_count": 3, "schema_version": 1},
        {"artifact_kind": "package_graph", "row_count": 2, "schema_version": 1},
        {"artifact_kind": "config_inventory", "row_count": 0, "schema_version": 1},
        {"artifact_kind": "project_model", "row_count": 1, "schema_version": 2},
        {"artifact_kind": "commit_log", "row_count": 1, "schema_version": 1},
    ]
    assert result.finalizing_payload == {
        "artifacts_total": 6,
        "commits_total": 1,
        "config_items_total": 0,
        "external_integrations_total": 0,
        "http_surface_detected": False,
        "package_edges_total": 1,
        "packages_total": 2,
        "snapshot_id": "snapshot-id",
        "symbols_total": 3,
        "touched_files_total": 3,
        "touched_packages_total": 2,
    }
    assert [event["progress_pct"] for event in progress_events] == [85, 90, 92, 93, 94, 95]
    assert alive_checks == 6

    package_graph = json.loads(result.artifacts[2].payload.decode("utf-8"))
    assert package_graph["entrypoints"][0]["package_id"] == "github.com/acme/project/cmd/api#main"


def test_publish_analysis_artifacts_uploads_and_registers_in_order() -> None:
    artifacts = (
        _artifact("file_inventory", "repositories/repo/snapshots/snapshot/analysis/file_inventory.schema-v1.json"),
        _artifact("go_symbols", "repositories/repo/snapshots/snapshot/analysis/go_symbols.schema-v1.json"),
    )
    storage = FakeStorage()
    repository_service = FakeRepositoryService()
    progress_events: list[dict[str, Any]] = []
    alive_checks = 0

    def report_progress(
        stage: str,
        progress_pct: int,
        message: str,
        *,
        progress_current: int = 0,
        progress_total: int = 0,
        payload: dict[str, Any] | None = None,
    ) -> None:
        progress_events.append(
            {
                "stage": stage,
                "progress_pct": progress_pct,
                "message": message,
                "progress_current": progress_current,
                "progress_total": progress_total,
                "payload": payload,
            }
        )

    def ensure_alive() -> None:
        nonlocal alive_checks
        alive_checks += 1

    publish_analysis_artifacts(
        storage=storage,
        repository_service=repository_service,
        repository_id="repo-id",
        snapshot_id="snapshot-id",
        index_run_id="run-id",
        artifacts=artifacts,
        report_progress=report_progress,
        ensure_alive=ensure_alive,
    )

    assert [upload["key"] for upload in storage.uploads] == [artifact.storage_key for artifact in artifacts]
    assert [upsert["artifact"]["artifact_kind"] for upsert in repository_service.upserts] == [
        "file_inventory",
        "go_symbols",
    ]
    assert repository_service.upserts[0]["artifact"] == {
        "artifact_kind": "file_inventory",
        "checksum_sha256": "checksum-file_inventory",
        "content_type": "application/json",
        "format": "json",
        "produced_by_index_run_id": "run-id",
        "row_count": 1,
        "schema_version": 1,
        "size_bytes": artifacts[0].size_bytes,
        "storage_bucket": "dopdoc-artifacts",
        "storage_key": artifacts[0].storage_key,
    }
    assert [event["progress_pct"] for event in progress_events] == [96, 97, 97]
    assert alive_checks == 6


def test_publish_analysis_artifacts_stops_before_register_when_upload_fails() -> None:
    artifacts = (
        _artifact("file_inventory", "repositories/repo/snapshots/snapshot/analysis/file_inventory.schema-v1.json"),
        _artifact("go_symbols", "repositories/repo/snapshots/snapshot/analysis/go_symbols.schema-v1.json"),
    )
    storage = FakeStorage(fail_on_key=artifacts[0].storage_key)
    repository_service = FakeRepositoryService()
    progress_events: list[dict[str, Any]] = []

    with pytest.raises(RuntimeError, match="upload failed"):
        publish_analysis_artifacts(
            storage=storage,
            repository_service=repository_service,
            repository_id="repo-id",
            snapshot_id="snapshot-id",
            index_run_id="run-id",
            artifacts=artifacts,
            report_progress=lambda *args, **kwargs: progress_events.append(
                {"stage": args[0], "progress_pct": args[1]}
            ),
            ensure_alive=lambda: None,
        )

    assert storage.uploads == []
    assert repository_service.upserts == []
    assert [event["progress_pct"] for event in progress_events] == [96]


def test_publish_analysis_artifacts_stops_after_upload_when_register_fails() -> None:
    artifacts = (
        _artifact("file_inventory", "repositories/repo/snapshots/snapshot/analysis/file_inventory.schema-v1.json"),
        _artifact("go_symbols", "repositories/repo/snapshots/snapshot/analysis/go_symbols.schema-v1.json"),
    )
    storage = FakeStorage()
    repository_service = FakeRepositoryService(fail_on_kind="file_inventory")
    progress_events: list[dict[str, Any]] = []
    alive_checks = 0

    def ensure_alive() -> None:
        nonlocal alive_checks
        alive_checks += 1

    with pytest.raises(RuntimeError, match="register failed"):
        publish_analysis_artifacts(
            storage=storage,
            repository_service=repository_service,
            repository_id="repo-id",
            snapshot_id="snapshot-id",
            index_run_id="run-id",
            artifacts=artifacts,
            report_progress=lambda *args, **kwargs: progress_events.append(
                {"stage": args[0], "progress_pct": args[1]}
            ),
            ensure_alive=ensure_alive,
        )

    assert [upload["key"] for upload in storage.uploads] == [artifacts[0].storage_key]
    assert [upsert["artifact"]["artifact_kind"] for upsert in repository_service.upserts] == [
        "file_inventory"
    ]
    assert [event["progress_pct"] for event in progress_events] == [96]
    assert alive_checks == 1


class FakeStorage:
    bucket = "dopdoc-artifacts"

    def __init__(self, fail_on_key: str | None = None) -> None:
        self.uploads: list[dict[str, Any]] = []
        self.fail_on_key = fail_on_key

    def put_bytes(self, key: str, data: bytes, content_type: str) -> None:
        if key == self.fail_on_key:
            raise RuntimeError("upload failed")

        self.uploads.append({"key": key, "data": data, "content_type": content_type})


class FakeRepositoryService:
    def __init__(self, fail_on_kind: str | None = None) -> None:
        self.upserts: list[dict[str, Any]] = []
        self.fail_on_kind = fail_on_kind

    def upsert_analysis_artifact(
        self,
        repository_id: str,
        snapshot_id: str,
        artifact: dict[str, Any],
    ) -> dict[str, Any]:
        self.upserts.append(
            {
                "repository_id": repository_id,
                "snapshot_id": snapshot_id,
                "artifact": artifact,
            }
        )
        if artifact["artifact_kind"] == self.fail_on_kind:
            raise RuntimeError("register failed")

        return {"id": f"{artifact['artifact_kind']}-id"}


def _artifact(artifact_kind: str, storage_key: str) -> BuiltAnalysisArtifact:
    payload = f'{{"artifact_kind":"{artifact_kind}"}}'.encode()
    return BuiltAnalysisArtifact(
        artifact_kind=artifact_kind,
        schema_version=1,
        format="json",
        content_type="application/json",
        storage_key=storage_key,
        checksum_sha256=f"checksum-{artifact_kind}",
        size_bytes=len(payload),
        row_count=1,
        payload=payload,
        summary={"row_count": 1},
    )


def _commit_all(repo: Repo, repo_root: Path) -> None:
    paths = [
        str(path.relative_to(repo_root))
        for path in sorted(repo_root.rglob("*"))
        if path.is_file() and ".git" not in path.parts
    ]
    repo.index.add(paths)
    actor = Actor("DopDoc", "dopdoc@example.com")
    repo.index.commit("init", author=actor, committer=actor)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
